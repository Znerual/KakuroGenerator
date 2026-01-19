"""
Database configuration and initialization.
Sets up SQLAlchemy engine and session management.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Database file path
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kakuro.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# Enable WAL mode for SQLite
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """
    FastAPI dependency for database sessions.
    Yields a database session and closes it after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()