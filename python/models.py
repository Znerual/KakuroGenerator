"""
SQLAlchemy ORM models for Kakuro Generator.
Defines User and Puzzle tables with relationships.
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from python.database import Base


def generate_uuid():
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class User(Base):
    """User account model."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Nullable for OAuth-only users
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    kakuros_solved = Column(Integer, default=0, nullable=False)
    
    # OAuth fields
    oauth_provider = Column(String(20), nullable=True)  # 'google', 'facebook', 'apple'
    oauth_id = Column(String(255), nullable=True)  # Provider's user ID
    
    # Relationships
    puzzles = relationship("Puzzle", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}>"


class Puzzle(Base):
    """Saved puzzle model with user association."""
    __tablename__ = "puzzles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    
    # Puzzle metadata
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    difficulty = Column(String(20), nullable=False)
    status = Column(String(20), default="started", nullable=False)  # 'started' or 'solved'
    
    # Puzzle data stored as JSON
    grid = Column(JSON, nullable=False)
    user_grid = Column(JSON, nullable=True)  # User's current progress
    row_notes = Column(JSON, default=list)
    col_notes = Column(JSON, default=list)
    cell_notes = Column(JSON, default=dict)
    notebook = Column(Text, default="")
    
    # Rating and feedback
    rating = Column(Integer, default=0)
    user_comment = Column(Text, default="")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="puzzles")

    def __repr__(self):
        return f"<Puzzle {self.id} ({self.difficulty})>"

    def to_dict(self):
        """Convert puzzle to dictionary for API response."""
        return {
            "id": self.id,
            "width": self.width,
            "height": self.height,
            "difficulty": self.difficulty,
            "status": self.status,
            "grid": self.grid,
            "userGrid": self.user_grid,
            "rowNotes": self.row_notes or [],
            "colNotes": self.col_notes or [],
            "cellNotes": self.cell_notes or {},
            "notebook": self.notebook or "",
            "rating": self.rating,
            "userComment": self.user_comment or "",
            "timestamp": self.created_at.isoformat() if self.created_at else None
        }
