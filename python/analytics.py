"""
Analytics service for tracking user sessions and puzzle interactions.
"""
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import Request
from python.models import UserSession, PuzzleInteraction, Puzzle
from python.kakuro import KakuroBoard # Needed to check correctness if required

def start_user_session(db: Session, user_id: str, request: Request, device_type: str = "desktop") -> UserSession:
    """
    Creates a new user session record upon login.
    Parses User-Agent and IP from the request.
    """
    user_agent = request.headers.get("user-agent", "")
    client_ip = request.client.host if request.client else None
    
    # Simple heuristic for OS/Browser (could be replaced with a library like user-agents)
    os_name = "Unknown"
    browser_name = "Unknown"
    
    if "Windows" in user_agent: os_name = "Windows"
    elif "Mac" in user_agent: os_name = "MacOS"
    elif "Linux" in user_agent: os_name = "Linux"
    elif "Android" in user_agent: os_name = "Android"
    elif "iPhone" in user_agent or "iPad" in user_agent: os_name = "iOS"

    if "Chrome" in user_agent: browser_name = "Chrome"
    elif "Firefox" in user_agent: browser_name = "Firefox"
    elif "Safari" in user_agent and "Chrome" not in user_agent: browser_name = "Safari"
    elif "Edg" in user_agent: browser_name = "Edge"

    session = UserSession(
        user_id=user_id,
        ip_address=client_ip,
        user_agent=user_agent,
        device_type=device_type,
        os=os_name,
        browser=browser_name,
        login_at=datetime.now(timezone.utc),
        last_activity_at=datetime.now(timezone.utc)
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def end_user_session(db: Session, session_id: str):
    """Marks a session as logged out."""
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if session:
        session.logout_at = datetime.now(timezone.utc)
        session.last_activity_at = datetime.now(timezone.utc)
        db.commit()

def log_interaction(
    db: Session, 
    user_id: str, 
    puzzle_id: str, 
    action_data: Dict[str, Any],
    session_id: Optional[str] = None
):
    """
    Logs a granular puzzle action.
    
    Expected action_data keys:
    - action_type: str (INPUT, DELETE, etc.)
    - row: int
    - col: int
    - old_value: str
    - new_value: str
    - duration_ms: int (time since last action)
    - device_type: str
    - client_timestamp: str (ISO format)
    """
    
    # Update session activity
    if session_id:
        session = db.query(UserSession).filter(UserSession.id == session_id).first()
        if session:
            session.last_activity_at = datetime.now(timezone.utc)

    # Calculate correctness if it's an input action
    is_correct = None
    if action_data.get('action_type') == 'INPUT' and action_data.get('new_value'):
        puzzle = db.query(Puzzle).filter(Puzzle.id == puzzle_id).first()
        if puzzle:
            # We need to look up the solution grid in the puzzle.grid JSON
            try:
                r, c = action_data.get('row'), action_data.get('col')
                if 0 <= r < len(puzzle.grid) and 0 <= c < len(puzzle.grid[0]):
                    target_cell = puzzle.grid[r][c]
                    # Logic assumes 'value' in grid is the solution value
                    # puzzle.grid is stored as list of dicts from JSON
                    sol_val = target_cell.get('value') 
                    input_val = int(action_data.get('new_value'))
                    is_correct = (sol_val == input_val)
            except Exception:
                pass

    interaction = PuzzleInteraction(
        user_id=user_id,
        puzzle_id=puzzle_id,
        session_id=session_id,
        action_type=action_data.get('action_type'),
        row=action_data.get('row'),
        col=action_data.get('col'),
        old_value=str(action_data.get('old_value')) if action_data.get('old_value') is not None else None,
        new_value=str(action_data.get('new_value')) if action_data.get('new_value') is not None else None,
        duration_ms=action_data.get('duration_ms'),
        device_type=action_data.get('device_type', 'desktop'),
        is_correct=is_correct,
        client_timestamp=datetime.fromisoformat(action_data.get('client_timestamp').replace('Z', '+00:00')) if action_data.get('client_timestamp') else None
    )

    db.add(interaction)
    db.commit()