"""
Pulse - Stalled Conversation Resurrection Engine

Streamlit app with three main features:
1. Classify & Nudge: Paste a transcript, get classification and nudge
2. Friction Heatmap: Analyze batch transcripts for drop-off points
3. Review Queue: Approve/Edit/Reject generated nudges
"""

import json
import time
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.models import (
    TranscriptInput,
    Message,
    MessageRole,
    BrandPersona,
    BRAND_PERSONAS,
    StallCategory,
    ReviewDecision,
)
from src.classifier import classify_transcript
from src.nudge_generator import generate_nudge, compare_brand_voices
from src.backend_status import check_backend_status, BackendStatusChecker
from src.friction_report import (
    generate_friction_report,
    generate_friction_report_by_type,
    print_friction_report,
)
from src.database import get_database, PulseDatabase


# Page config
st.set_page_config(
    page_title="Pulse - Conversation Resurrection",
    page_icon="💓",
    layout="wide",
)

# Custom CSS
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
    }
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .nudge-box {
        background-color: #e8f4ea;
        border-left: 4px solid #28a745;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .warning-box {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)


def parse_transcript_input(text: str) -> TranscriptInput:
    """Parse user input into TranscriptInput format."""
    lines = text.strip().split("\n")
    history = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Try to parse "BOT: message" or "USER: message" format
        if line.upper().startswith("BOT:"):
            history.append(Message(
                role=MessageRole.BOT,
                text=line[4:].strip()
            ))
        elif line.upper().startswith("USER:"):
            history.append(Message(
                role=MessageRole.USER,
                text=line[5:].strip()
            ))
        elif line.upper().startswith("AGENT:"):
            history.append(Message(
                role=MessageRole.BOT,
                text=line[6:].strip()
            ))
        elif line.upper().startswith("CUSTOMER:"):
            history.append(Message(
                role=MessageRole.USER,
                text=line[9:].strip()
            ))
        else:
            # Try to append to last message or create new one
            if history:
                history[-1].text += " " + line
            else:
                history.append(Message(role=MessageRole.USER, text=line))
    
    return TranscriptInput(
        chat_id=f"manual-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        history=history,
    )


def render_classify_nudge_tab():
    """Render the Classify & Nudge tab."""
    st.header("Classify & Nudge")
    st.markdown("""
    Paste a conversation transcript to classify why the user stalled and generate a contextual nudge.
    """)
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Input Transcript")
        
        # Sample transcript for demo
        sample = """BOT: Hi! I can help you get an auto insurance quote. To get started, I'll need your VIN number.
USER: Ugh, I'm at work right now. I don't have that on me.
BOT: No problem! You can usually find your VIN on your insurance card or registration document."""
        
        transcript_text = st.text_area(
            "Paste transcript (format: BOT: message / USER: message)",
            value=sample,
            height=200,
        )
        
        # Brand voice selection
        brand_persona = st.selectbox(
            "Brand Voice",
            options=[bp.value for bp in BrandPersona],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        
        # Multi-channel awareness
        st.markdown("---")
        st.markdown("**Multi-Channel Awareness**")
        mock_active_elsewhere = st.checkbox(
            "Simulate user active on another channel (portal/email)",
            value=False,
            help="If checked, simulates a user who completed the action elsewhere"
        )
        
        classify_btn = st.button("Classify & Generate Nudge", type="primary")
    
    with col2:
        st.subheader("Results")
        
        if classify_btn and transcript_text:
            try:
                # Parse transcript
                transcript = parse_transcript_input(transcript_text)
                
                if len(transcript.history) < 2:
                    st.error("Please provide at least 2 messages (bot and user)")
                    return
                
                # Check backend status first
                with st.spinner("Checking multi-channel status..."):
                    backend_status = check_backend_status(
                        transcript.chat_id,
                        mock_mode=True,
                        mock_active_elsewhere_rate=1.0 if mock_active_elsewhere else 0.0
                    )
                
                if not backend_status.safe_to_nudge:
                    st.markdown("""
                    <div class="warning-box">
                        <strong>⚠️ User Active Elsewhere</strong><br>
                        This user has taken action on another channel. 
                        <strong>Do NOT send a nudge</strong> - it would be annoying.
                    </div>
                    """, unsafe_allow_html=True)
                    st.json({
                        "user_active_elsewhere": backend_status.user_active_elsewhere,
                        "last_portal_activity": str(backend_status.last_portal_activity),
                        "safe_to_nudge": backend_status.safe_to_nudge,
                    })
                    return
                
                # Classify
                with st.spinner("Classifying transcript..."):
                    start = time.time()
                    classification = classify_transcript(transcript)
                    classify_time = time.time() - start
                
                # Display classification
                st.markdown("### Classification")
                
                status_colors = {
                    "STALLED_HIGH_RISK": "🔴",
                    "STALLED_LOW_RISK": "🟡",
                    "BENIGN": "🟢",
                }
                
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.metric("Status", f"{status_colors.get(classification.status.value, '')} {classification.status.value}")
                with col_b:
                    st.metric("Category", classification.category.value)
                with col_c:
                    st.metric("Confidence", f"{classification.confidence:.0%}")
                
                st.markdown(f"**Reason:** {classification.reason}")
                st.markdown(f"**Evidence:** _{classification.evidence}_")
                st.caption(f"Classification took {classify_time*1000:.0f}ms")
                
                # Generate nudge if not benign
                if classification.category != StallCategory.BENIGN:
                    st.markdown("---")
                    st.markdown("### Suggested Nudge")
                    
                    with st.spinner("Generating nudge..."):
                        start = time.time()
                        nudge = generate_nudge(
                            transcript,
                            classification,
                            BrandPersona(brand_persona),
                        )
                        nudge_time = time.time() - start
                    
                    st.markdown(f"""
                    <div class="nudge-box">
                        <strong>💬 {brand_persona.replace('_', ' ').title()}</strong><br>
                        "{nudge.nudge_text}"
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.caption(f"Length: {len(nudge.nudge_text)} chars | Generation took {nudge_time*1000:.0f}ms")
                    
                    # Compare both voices
                    with st.expander("Compare Both Brand Voices"):
                        all_nudges = compare_brand_voices(transcript, classification)
                        for persona, n in all_nudges.items():
                            st.markdown(f"**{persona.value.replace('_', ' ').title()}:**")
                            st.markdown(f"> {n.nudge_text}")
                            st.caption(f"Length: {len(n.nudge_text)} chars")
                else:
                    st.info("Classification is BENIGN - no nudge recommended. User is likely just busy.")
                    
            except Exception as e:
                st.error(f"Error: {str(e)}")
                st.exception(e)


def render_friction_heatmap_tab():
    """Render the Friction Heatmap tab."""
    st.header("Friction Heatmap")
    st.markdown("""
    Analyze batch transcripts to identify which bot questions cause the most user drop-off.
    This acts as a **debugger for your conversation flow**.
    """)
    
    # Load sample data or upload
    data_source = st.radio(
        "Data Source",
        ["Use Sample Data", "Upload JSON File"],
        horizontal=True,
    )
    
    transcripts = []
    classifications = []
    
    if data_source == "Use Sample Data":
        if st.button("Load & Analyze Sample Data", type="primary"):
            with st.spinner("Loading sample transcripts and classifying..."):
                # Load sample transcripts
                try:
                    with open("data/sample_transcripts.json", "r") as f:
                        data = json.load(f)
                    with open("data/sample_transcripts_extended.json", "r") as f:
                        data2 = json.load(f)
                    
                    all_transcripts = data.get("transcripts", []) + data2.get("transcripts", [])
                    
                    progress = st.progress(0)
                    for i, t in enumerate(all_transcripts):
                        transcript = TranscriptInput(
                            chat_id=t["chat_id"],
                            history=[
                                Message(role=MessageRole(m["role"]), text=m["text"])
                                for m in t["history"]
                            ]
                        )
                        transcripts.append(transcript)
                        
                        # Classify
                        result = classify_transcript(transcript)
                        classifications.append(result)
                        
                        progress.progress((i + 1) / len(all_transcripts))
                    
                    st.session_state["friction_transcripts"] = transcripts
                    st.session_state["friction_classifications"] = classifications
                    
                except FileNotFoundError:
                    st.error("Sample data files not found. Please ensure data/sample_transcripts.json exists.")
                    return
    else:
        uploaded_file = st.file_uploader("Upload transcripts JSON", type=["json"])
        if uploaded_file:
            data = json.load(uploaded_file)
            # Process uploaded data...
            st.info("Processing uploaded data...")
    
    # Display results if we have data
    if "friction_classifications" in st.session_state:
        transcripts = st.session_state["friction_transcripts"]
        classifications = st.session_state["friction_classifications"]
        
        st.success(f"Analyzed {len(classifications)} transcripts")
        
        # Generate report
        report = generate_friction_report(transcripts, classifications, min_occurrences=1)
        by_type = generate_friction_report_by_type(transcripts, classifications)
        
        # Summary metrics
        st.markdown("---")
        st.subheader("Summary")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Analyzed", report.total_conversations)
        with col2:
            st.metric("Friction Rate", f"{report.overall_friction_rate:.0%}")
        with col3:
            st.metric("High Friction", report.by_category.get("HIGH_FRICTION", 0))
        with col4:
            st.metric("Confusion", report.by_category.get("CONFUSION", 0))
        
        # Charts
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("By Category")
            if report.by_category:
                fig = px.pie(
                    values=list(report.by_category.values()),
                    names=list(report.by_category.keys()),
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("By Question Type")
            if by_type:
                df = pd.DataFrame([
                    {"Type": k, "Friction Rate": v["friction_rate"], "Count": v["total"]}
                    for k, v in by_type.items()
                ]).sort_values("Friction Rate", ascending=False)
                
                fig = px.bar(
                    df,
                    x="Type",
                    y="Friction Rate",
                    color="Friction Rate",
                    color_continuous_scale="RdYlGn_r",
                )
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)
        
        # Top friction points table
        st.markdown("---")
        st.subheader("Top Friction Points")
        st.markdown("_Bot questions causing the most user drop-off:_")
        
        if report.top_friction_points:
            table_data = []
            for fp in report.top_friction_points[:10]:
                table_data.append({
                    "Bot Question": fp.bot_question[:60] + "..." if len(fp.bot_question) > 60 else fp.bot_question,
                    "Occurrences": fp.total_occurrences,
                    "Friction": fp.friction_count,
                    "Rate": f"{fp.friction_rate:.0%}",
                })
            
            st.dataframe(
                pd.DataFrame(table_data),
                use_container_width=True,
                hide_index=True,
            )
        
        # Actionable insights
        st.markdown("---")
        st.subheader("💡 Actionable Insights")
        
        if report.top_friction_points:
            top = report.top_friction_points[0]
            st.markdown(f"""
            **Top Issue:** "{top.bot_question[:80]}..."
            
            This question causes **{top.friction_rate:.0%}** of users to stall ({top.friction_count} out of {top.total_occurrences}).
            
            **Recommendations:**
            - Consider offering alternative ways to provide this information
            - Make the request optional if possible
            - Provide clearer instructions on where to find this data
            - Consider asking for this information later in the flow
            """)


def render_review_queue_tab():
    """Render the Review Queue tab."""
    st.header("Review Queue")
    st.markdown("""
    Review generated nudges before they're sent. Approve, edit, or reject each one.
    """)
    
    db = get_database()
    
    # Stats
    stats = db.get_review_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Reviewed", stats["total"])
    with col2:
        st.metric("Approved", stats["approved"])
    with col3:
        st.metric("Approval Rate", f"{stats['approval_rate']:.0%}")
    with col4:
        st.metric("Avg Review Time", f"{stats['avg_review_time']:.1f}s")
    
    st.markdown("---")
    
    # Get nudges pending review
    pending = db.get_nudges_for_review(limit=20)
    
    if not pending:
        st.info("No nudges pending review. Generate some nudges from the Classify & Nudge tab first!")
        
        # Demo mode
        if st.button("Generate Demo Nudges"):
            with st.spinner("Generating demo nudges..."):
                # Load sample and generate
                try:
                    with open("data/sample_transcripts.json", "r") as f:
                        data = json.load(f)
                    
                    for t in data["transcripts"][:5]:
                        transcript = TranscriptInput(
                            chat_id=t["chat_id"],
                            history=[
                                Message(role=MessageRole(m["role"]), text=m["text"])
                                for m in t["history"]
                            ]
                        )
                        
                        db.save_transcript(transcript)
                        classification = classify_transcript(transcript)
                        class_id = db.save_classification(classification)
                        
                        if classification.category != StallCategory.BENIGN:
                            nudge = generate_nudge(transcript, classification)
                            db.save_nudge(nudge, class_id)
                    
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        return
    
    st.subheader(f"Pending Review ({len(pending)})")
    
    for item in pending:
        with st.expander(f"📝 {item['chat_id']} - {item['category']}", expanded=False):
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.markdown("**Conversation:**")
                for msg in item["history"]:
                    role = "🤖" if msg["role"] == "bot" else "👤"
                    st.markdown(f"{role} {msg['text']}")
                
                st.markdown(f"**Classification:** {item['category']} (confidence: {item['confidence']:.0%})")
            
            with col2:
                st.markdown("**Suggested Nudge:**")
                st.markdown(f"""
                <div class="nudge-box">
                    "{item['nudge_text']}"
                </div>
                """, unsafe_allow_html=True)
                st.caption(f"Brand: {item['brand_persona']} | Length: {len(item['nudge_text'])} chars")
                
                # Edit field
                edited = st.text_area(
                    "Edit nudge (optional)",
                    value=item["nudge_text"],
                    key=f"edit_{item['nudge_id']}",
                    height=80,
                )
                
                # Action buttons
                bcol1, bcol2, bcol3 = st.columns(3)
                
                with bcol1:
                    if st.button("✅ Approve", key=f"approve_{item['nudge_id']}"):
                        decision = ReviewDecision.EDITED if edited != item["nudge_text"] else ReviewDecision.APPROVED
                        db.save_review(
                            item["nudge_id"],
                            decision,
                            edited_text=edited if edited != item["nudge_text"] else None,
                        )
                        st.success("Approved!")
                        st.rerun()
                
                with bcol2:
                    if st.button("✏️ Edit & Approve", key=f"edit_approve_{item['nudge_id']}"):
                        db.save_review(
                            item["nudge_id"],
                            ReviewDecision.EDITED,
                            edited_text=edited,
                        )
                        st.success("Edited and approved!")
                        st.rerun()
                
                with bcol3:
                    if st.button("❌ Reject", key=f"reject_{item['nudge_id']}"):
                        db.save_review(
                            item["nudge_id"],
                            ReviewDecision.REJECTED,
                        )
                        st.warning("Rejected")
                        st.rerun()


def main():
    """Main app entry point."""
    st.title("💓 Pulse")
    st.markdown("*Stalled Conversation Resurrection Engine*")
    
    # Tabs
    tab1, tab2, tab3 = st.tabs([
        "🔍 Classify & Nudge",
        "🔥 Friction Heatmap",
        "📋 Review Queue",
    ])
    
    with tab1:
        render_classify_nudge_tab()
    
    with tab2:
        render_friction_heatmap_tab()
    
    with tab3:
        render_review_queue_tab()
    
    # Footer
    st.markdown("---")
    st.caption("Pulse v0.1.0 | Built for General Magic")


if __name__ == "__main__":
    main()
