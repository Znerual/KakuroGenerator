"""
Database configuration and session management for Kakuro Generator.
Uses SQLite for local storage via SQLAlchemy.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import sys


def get_database_path():
    """Get the path for the SQLite database file."""
    if getattr(sys, 'frozen', False):
        # Running as bundled executable
        base_dir = os.path.dirname(sys.executable)
    else:
        # Normal Python environment
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_dir, "kakuro.db")


DATABASE_URL = f"sqlite:///{get_database_path()}"

# Create engine with SQLite-specific settings
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite with FastAPI
    echo=False  # Set to True for SQL debugging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


def get_db():
    """
    Dependency that provides a database session.
    Use with FastAPI's Depends() for automatic session management.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize the database by creating all tables.
    Should be called once at application startup.
    """
    # Import models to ensure they're registered with Base
    import python.models as models  # noqa: F401
    Base.metadata.create_all(bind=engine)
