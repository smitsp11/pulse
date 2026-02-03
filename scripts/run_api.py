#!/usr/bin/env python3
"""
Run the Pulse API server.

Usage:
    python scripts/run_api.py
    
Or with uvicorn directly:
    uvicorn src.api:app --reload --host 0.0.0.0 --port 8000
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn

if __name__ == "__main__":
    print("Starting Pulse API server...")
    print("API docs will be available at: http://localhost:8000/docs")
    print("Health check: http://localhost:8000/health")
    print()
    
    uvicorn.run(
        "src.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
