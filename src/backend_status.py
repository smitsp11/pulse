"""
Backend status checker for multi-channel state awareness.

This module provides a placeholder implementation for checking if a user
has taken action on other channels (web portal, email, phone) while
silent on SMS.

CRITICAL: This prevents the "Multi-Channel State Trap" where we nudge
a user who has already completed the requested action elsewhere.
"""

from datetime import datetime, timedelta
from typing import Optional
import random

from .models import BackendStatus


def check_backend_status(
    chat_id: str,
    mock_mode: bool = True,
    mock_active_elsewhere_rate: float = 0.0
) -> BackendStatus:
    """
    Check if user has been active on other channels.
    
    In production, this queries the CRM/portal to check:
    - Did user upload requested document via web portal?
    - Did user email the agent directly?
    - Did user call the agency?
    
    If any of these are true, DO NOT nudge—the silence is resolved.
    
    Args:
        chat_id: The conversation ID to check
        mock_mode: If True, return mock data (for development)
        mock_active_elsewhere_rate: Probability of mock returning active_elsewhere=True
        
    Returns:
        BackendStatus indicating whether it's safe to nudge
    """
    if mock_mode:
        return _mock_backend_check(chat_id, mock_active_elsewhere_rate)
    
    # TODO: Implement real backend integration
    # This would typically involve:
    # 1. Query CRM API for recent activity on this chat_id
    # 2. Check document upload service for pending uploads
    # 3. Check email inbox for messages from this user
    # 4. Check call logs for recent calls
    
    raise NotImplementedError(
        "Real backend integration not yet implemented. "
        "Set mock_mode=True for development."
    )


def _mock_backend_check(
    chat_id: str,
    active_elsewhere_rate: float = 0.0
) -> BackendStatus:
    """
    Mock implementation for development and testing.
    
    Args:
        chat_id: The conversation ID
        active_elsewhere_rate: Probability of returning active_elsewhere=True
        
    Returns:
        Mock BackendStatus
    """
    # Simulate some users being active elsewhere
    is_active_elsewhere = random.random() < active_elsewhere_rate
    
    if is_active_elsewhere:
        # Simulate user uploaded document via portal
        return BackendStatus(
            chat_id=chat_id,
            user_active_elsewhere=True,
            last_portal_activity=datetime.utcnow() - timedelta(minutes=random.randint(5, 60)),
            pending_documents_received=True,
            safe_to_nudge=False,
        )
    
    # Default: no activity elsewhere, safe to nudge
    return BackendStatus(
        chat_id=chat_id,
        user_active_elsewhere=False,
        last_portal_activity=None,
        pending_documents_received=False,
        safe_to_nudge=True,
    )


class BackendStatusChecker:
    """
    Backend status checker with configurable behavior.
    
    This class allows for dependency injection and easier testing.
    """
    
    def __init__(
        self,
        mock_mode: bool = True,
        mock_active_elsewhere_rate: float = 0.0,
        crm_api_url: Optional[str] = None,
        crm_api_key: Optional[str] = None,
    ):
        """
        Initialize the backend status checker.
        
        Args:
            mock_mode: If True, use mock implementation
            mock_active_elsewhere_rate: For mock mode, probability of active elsewhere
            crm_api_url: URL for CRM API (for production mode)
            crm_api_key: API key for CRM (for production mode)
        """
        self.mock_mode = mock_mode
        self.mock_active_elsewhere_rate = mock_active_elsewhere_rate
        self.crm_api_url = crm_api_url
        self.crm_api_key = crm_api_key
    
    def check(self, chat_id: str) -> BackendStatus:
        """
        Check backend status for a conversation.
        
        Args:
            chat_id: The conversation ID to check
            
        Returns:
            BackendStatus indicating whether it's safe to nudge
        """
        return check_backend_status(
            chat_id=chat_id,
            mock_mode=self.mock_mode,
            mock_active_elsewhere_rate=self.mock_active_elsewhere_rate,
        )
    
    def check_batch(self, chat_ids: list[str]) -> dict[str, BackendStatus]:
        """
        Check backend status for multiple conversations.
        
        Args:
            chat_ids: List of conversation IDs to check
            
        Returns:
            Dictionary mapping chat_id to BackendStatus
        """
        return {chat_id: self.check(chat_id) for chat_id in chat_ids}


# Example production implementation sketch
"""
def _real_backend_check(chat_id: str, crm_api_url: str, crm_api_key: str) -> BackendStatus:
    '''
    Real implementation that queries General Magic backend.
    
    This is a sketch of what the production implementation would look like.
    '''
    import requests
    
    # Query CRM for recent activity
    response = requests.get(
        f"{crm_api_url}/conversations/{chat_id}/activity",
        headers={"Authorization": f"Bearer {crm_api_key}"},
        timeout=5,
    )
    
    if response.status_code != 200:
        # Default to safe_to_nudge=True if we can't check
        # (fail open rather than block all nudges)
        return BackendStatus(
            chat_id=chat_id,
            user_active_elsewhere=False,
            safe_to_nudge=True,
        )
    
    data = response.json()
    
    return BackendStatus(
        chat_id=chat_id,
        user_active_elsewhere=data.get("has_recent_activity", False),
        last_portal_activity=datetime.fromisoformat(data["last_activity"]) if data.get("last_activity") else None,
        pending_documents_received=data.get("documents_received", False),
        safe_to_nudge=not data.get("has_recent_activity", False),
    )
"""


if __name__ == "__main__":
    # Example usage
    print("Testing backend status checker...")
    
    # Mock mode - always safe to nudge
    checker = BackendStatusChecker(mock_mode=True, mock_active_elsewhere_rate=0.0)
    status = checker.check("test-001")
    print(f"\nWith 0% active elsewhere rate:")
    print(f"  Safe to nudge: {status.safe_to_nudge}")
    print(f"  User active elsewhere: {status.user_active_elsewhere}")
    
    # Mock mode - 50% chance of being active elsewhere
    checker = BackendStatusChecker(mock_mode=True, mock_active_elsewhere_rate=0.5)
    print(f"\nWith 50% active elsewhere rate (5 samples):")
    for i in range(5):
        status = checker.check(f"test-{i:03d}")
        print(f"  Chat {status.chat_id}: safe_to_nudge={status.safe_to_nudge}")
