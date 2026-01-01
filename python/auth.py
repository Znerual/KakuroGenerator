"""
Authentication utilities for Kakuro Generator.
Handles password hashing, JWT token management, email verification, and password reset.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from python.database import get_db
from python.models import User
import python.config as config
import random
import string

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)

import bcrypt

# Hash a password using bcrypt
def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password=pwd_bytes, salt=salt)
    return hashed_password.decode('utf-8')  # Return as string for DB storage

# Check if the provided password matches the stored password (hashed)
def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_byte_enc = plain_password.encode('utf-8')
    hashed_byte_enc = hashed_password.encode('utf-8')  # Convert stored string back to bytes
    return bcrypt.checkpw(password=password_byte_enc, hashed_password=hashed_byte_enc)


def generate_verification_code(length: int = 6) -> str:
    """Generate a numeric verification code."""
    return ''.join(random.choices(string.digits, k=length))

def create_access_token(user_id: str, session_id: Optional[str] = None, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: The user's unique ID to encode in the token
        session_id: The ID of the current login session (UserSession)
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token string
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        "sub": user_id,
        "sid": session_id,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def create_refresh_token(user_id: str, session_id: Optional[str] = None) -> str:
    """
    Create a JWT refresh token with longer expiration.
    
    Args:
        user_id: The user's unique ID to encode in the token
        session_id: The ID of the current login session

    Returns:
        Encoded JWT refresh token string
    """
    expire = datetime.now(timezone.utc) + timedelta(days=config.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "sid": session_id,
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def create_email_verification_token(user_id: str, email: str) -> str:
    """
    Create a JWT token for email verification.
    
    Args:
        user_id: The user's unique ID
        email: The email address to verify
        
    Returns:
        Encoded JWT token string
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=config.EMAIL_VERIFICATION_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "type": "email_verification"
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def create_password_reset_token(user_id: str, email: str) -> str:
    """
    Create a JWT token for password reset.
    
    Args:
        user_id: The user's unique ID
        email: The user's email address
        
    Returns:
        Encoded JWT token string
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=config.PASSWORD_RESET_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "type": "password_reset"
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str, expected_type: Optional[str] = None) -> Optional[dict]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: The JWT token string to decode
        expected_type: Optional type to validate (e.g., 'email_verification', 'password_reset')
        
    Returns:
        Token payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
        
        # Validate token type if specified
        if expected_type and payload.get("type") != expected_type:
            return None
            
        return payload
    except JWTError:
        return None


def verify_email_token(token: str) -> Optional[dict]:
    """
    Verify an email verification token.
    
    Returns:
        Dictionary with 'user_id' and 'email' if valid, None otherwise
    """
    payload = decode_token(token, expected_type="email_verification")
    if payload:
        return {
            "user_id": payload.get("sub"),
            "email": payload.get("email")
        }
    return None


def verify_password_reset_token(token: str) -> Optional[dict]:
    """
    Verify a password reset token.
    
    Returns:
        Dictionary with 'user_id' and 'email' if valid, None otherwise
    """
    payload = decode_token(token, expected_type="password_reset")
    if payload:
        return {
            "user_id": payload.get("sub"),
            "email": payload.get("email")
        }
    return None

def get_current_user_and_session(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> tuple[Optional[User], Optional[str]]:
    """
    FastAPI dependency to get the current authenticated user AND their session ID.
    Returns (None, None) if no valid token is provided.
    """
    if not credentials:
        return None, None
    
    payload = decode_token(credentials.credentials)
    if not payload:
        return None, None
    
    user_id = payload.get("sub")
    session_id = payload.get("sid") # Extract Session ID
    
    if not user_id:
        return None, None
    
    user = db.query(User).filter(User.id == user_id).first()
    return user, session_id

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Legacy wrapper for getting just the user.
    """
    user, _ = get_current_user_and_session(credentials, db)
    return user

def get_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to require an admin user.
    Raises 403 Forbidden if the user is not an admin.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative access required"
        )
    return current_user


def get_required_user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db)
) -> User:
    """
    FastAPI dependency to require an authenticated user.
    Raises 401 Unauthorized if no valid token is provided.
    
    Use this for protected endpoints that require authentication.
    """
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user