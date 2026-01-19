"""
Database models for Kakuro Generator.
Defines User and Puzzle models with SQLAlchemy.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, JSON, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base
import uuid

def generate_uuid():
    return str(uuid.uuid4())

def generate_short_id(length=8):
    """Generates a short, readable unique ID."""
    import secrets
    import string
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
    
class User(Base):
    """User model for authentication and profile management."""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=True)
    password_hash = Column(String, nullable=True)  # Null for OAuth users
    
    # Email verification
    email_verified = Column(Boolean, default=False, nullable=False)
    
    # OAuth fields
    oauth_provider = Column(String, nullable=True)  # 'google', 'facebook', 'apple', or None
    oauth_id = Column(String, nullable=True)  # Provider's user ID

    verification_code = Column(String, nullable=True)
    verification_code_expires_at = Column(DateTime, nullable=True)
    
    # Profile
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    
    # Statistics
    kakuros_solved = Column(Integer, default=0)
    total_score = Column(Integer, default=0)
    is_admin = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    puzzles = relationship("Puzzle", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    interactions = relationship("PuzzleInteraction", back_populates="user", cascade="all, delete-orphan")
    scores = relationship("ScoreRecord", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self):
        """Convert user to dictionary for API responses."""
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "email_verified": self.email_verified,
            "oauth_provider": self.oauth_provider,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "kakuros_solved": self.kakuros_solved,
            "total_score": self.total_score,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }

class UserSession(Base):
    """Tracks user login sessions, device info, and duration."""
    __tablename__ = "user_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    # Session Timings
    login_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_activity_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    logout_at = Column(DateTime, nullable=True)
    
    # Device / Context Info
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    device_type = Column(String, nullable=True)  # 'mobile', 'desktop', 'tablet'
    browser = Column(String, nullable=True)
    os = Column(String, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    interactions = relationship("PuzzleInteraction", back_populates="session")

class PuzzleTemplate(Base):
    """
    Represents the immutable definition of a puzzle (the 'level').
    Multiple users can solve the same PuzzleTemplate.
    """
    __tablename__ = "puzzle_templates"

    id = Column(String, primary_key=True, default=generate_uuid)
    
    # Metadata
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    difficulty = Column(String, nullable=False)

    difficulty_score = Column(Float, nullable=False)
    difficulty_data = Column(JSON, nullable=False)
    
    # The immutable puzzle data
    grid = Column(JSON, nullable=False) # The structure: black cells, clues
    solution = Column(JSON, nullable=True) # The specific solution (optional, if we want to validate on backend)
    
    # Generation info
    seed = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Freshness tracking - how many times this puzzle has been served
    times_used = Column(Integer, default=0, nullable=False)
    
    # Quality tracking - how many users skipped this puzzle without completing
    times_skipped = Column(Integer, default=0, nullable=False)

    # Relationships
    puzzles = relationship("Puzzle", back_populates="template")

class DifficultyStat(Base):
    """Stores running totals to calculate means efficiently."""
    __tablename__ = "difficulty_stats"
    
    difficulty = Column(String, primary_key=True) # very_easy, easy, etc.
    sum_scores = Column(Float, default=0.0, nullable=False)
    count = Column(Integer, default=0, nullable=False)

    @property
    def mean(self) -> float:
        return self.sum_scores / self.count if self.count > 0 else 0.0

class Puzzle(Base):
    """Puzzle model for storing user's saved puzzles."""
    __tablename__ = "puzzles"
    
    id = Column(String, primary_key=True)
    short_id = Column(String, unique=True, nullable=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    template_id = Column(String, ForeignKey("puzzle_templates.id"), nullable=True, index=True)
    
    # Puzzle configuration
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    difficulty = Column(String, nullable=False)
    
    # Puzzle data (stored as JSON)
    grid = Column(JSON, nullable=False)
    user_grid = Column(JSON, nullable=True)
    
    # User notes
    row_notes = Column(JSON, default=list)
    col_notes = Column(JSON, default=list)
    cell_notes = Column(JSON, default=dict)
    notebook = Column(Text, default="")
    
    # User feedback
    rating = Column(Integer, default=0)
    user_comment = Column(Text, default="")
    difficulty_vote = Column(Integer, nullable=True) # 1-10 scale
    
    # Status
    status = Column(String, default="started")  # 'started', 'solved', 'given_up'
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="puzzles")
    template = relationship("PuzzleTemplate", back_populates="puzzles")
    interactions = relationship("PuzzleInteraction", back_populates="puzzle", cascade="all, delete-orphan")
    
    def to_dict(self):
        """Convert puzzle to dictionary for API responses."""
        return {
            "id": self.id,
            "width": self.width,
            "height": self.height,
            "difficulty": self.difficulty,
            "grid": self.grid,
            "userGrid": self.user_grid,
            "rowNotes": self.row_notes,
            "colNotes": self.col_notes,
            "cellNotes": self.cell_notes,
            "notebook": self.notebook,
            "rating": self.rating,
            "difficultyVote": self.difficulty_vote,
            "userComment": self.user_comment,
            "status": self.status,
            "timestamp": self.created_at.isoformat() if self.created_at else None,
            "template_id": self.template_id,
            "short_id": self.short_id
        }

class PuzzleInteraction(Base):
    """
    Granular log of every action taken on a puzzle.
    Allows replaying the game and analyzing solving patterns.
    """
    __tablename__ = "puzzle_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    puzzle_id = Column(String, ForeignKey("puzzles.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    session_id = Column(String, ForeignKey("user_sessions.id"), nullable=True)

    # Action details
    action_type = Column(String, nullable=False) 
    # Types: 'INPUT', 'DELETE', 'NOTE_ADD', 'NOTE_REMOVE', 'UNDO', 'REDO', 'CHECK', 'PAUSE', 'RESUME', 'SOLVED'
    
    # Coordinates (if applicable)
    row = Column(Integer, nullable=True)
    col = Column(Integer, nullable=True)
    
    # Value changes
    old_value = Column(String, nullable=True) # Stored as string to handle '1', '1,2' (notes), or NULL
    new_value = Column(String, nullable=True)
    
    # Metadata
    is_correct = Column(Boolean, nullable=True) # Was the input correct according to solution?
    
    # Timing
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    client_timestamp = Column(DateTime, nullable=True) # Time on user's device
    duration_ms = Column(Integer, nullable=True) # Time taken since last action (think time)
    
    # Progress
    fill_count = Column(Integer, nullable=True) # How many white cells are filled at this moment
    
    # Device context (in case they switch devices mid-puzzle)
    device_type = Column(String, nullable=True) # 'mobile', 'desktop'

    # Relationships
    puzzle = relationship("Puzzle", back_populates="interactions")
    user = relationship("User", back_populates="interactions")
    session = relationship("UserSession", back_populates="interactions")

class PerformanceMetric(Base):
    """
    Stores various performance metrics for the system and application.
    """
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_name = Column(String, nullable=False, index=True) # e.g., 'queue_fill_time', 'request_duration'
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=True) # e.g., 'ms', '%', 'bytes'
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    metadata_json = Column(JSON, nullable=True) # Extra context (route, difficulty, etc.)

    def to_dict(self):
        return {
            "id": self.id,
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata_json
        }

class AuthLog(Base):
    """
    Logs login and registration attempts, including IP addresses and success status.
    """
    __tablename__ = "auth_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    email = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False) # 'LOGIN', 'REGISTER', 'GOOGLE_LOGIN', etc.
    status = Column(String, nullable=False) # 'SUCCESS', 'FAILURE', 'LOCKED'
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    reason = Column(String, nullable=True) # e.g., 'Invalid password', 'User not found'
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "email": self.email,
            "action": self.action,
            "status": self.status,
            "ip_address": self.ip_address,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

class ScoreRecord(Base):
    """
    Tracks individual scores gained for each solved puzzle.
    Used for monthly and all-time leaderboards.
    """
    __tablename__ = "score_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    puzzle_id = Column(String, ForeignKey("puzzles.id"), nullable=False, index=True)
    points = Column(Integer, nullable=False)
    difficulty = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    user = relationship("User", back_populates="scores")