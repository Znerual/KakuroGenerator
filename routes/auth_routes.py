"""
Authentication routes for Kakuro Generator.
Handles user registration, login, OAuth, and profile management.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from python.database import get_db
from python.models import User
from python.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    get_required_user, get_current_user
)
import python.oauth as oauth_module
import python.config as config

router = APIRouter(prefix="/auth", tags=["authentication"])


# =====================
# Request/Response Models
# =====================

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    created_at: datetime
    last_login: Optional[datetime]
    kakuros_solved: int
    oauth_provider: Optional[str]


class RefreshRequest(BaseModel):
    refresh_token: str


# =====================
# Registration & Login
# =====================

@router.post("/register", response_model=TokenResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user account."""
    
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username already exists
    existing_username = db.query(User).filter(User.username == request.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Validate password
    if len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters"
        )
    
    # Create user
    user = User(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
        last_login=datetime.utcnow()
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Login with email and password."""
    
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(request: RefreshRequest, db: Session = Depends(get_db)):
    """Refresh an access token using a refresh token."""
    
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Generate new tokens
    access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)
    
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


# =====================
# User Profile
# =====================

@router.get("/me", response_model=UserResponse)
def get_profile(user: User = Depends(get_required_user)):
    """Get the current user's profile."""
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        created_at=user.created_at,
        last_login=user.last_login,
        kakuros_solved=user.kakuros_solved,
        oauth_provider=user.oauth_provider
    )


# =====================
# OAuth Routes
# =====================

@router.get("/google")
async def google_auth(request: Request):
    """Redirect to Google OAuth."""
    if not config.is_google_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured"
        )
    redirect = await oauth_module.get_oauth_authorize_redirect('google', request)
    return redirect


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Google OAuth callback."""
    user_info = await oauth_module.get_google_user_info(request)
    
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google authentication failed"
        )
    
    # Find or create user
    user = db.query(User).filter(
        User.oauth_provider == 'google',
        User.oauth_id == user_info['oauth_id']
    ).first()
    
    if not user:
        # Check if email exists with different provider
        existing_email = db.query(User).filter(User.email == user_info['email']).first()
        if existing_email:
            # Link accounts by updating existing user
            existing_email.oauth_provider = 'google'
            existing_email.oauth_id = user_info['oauth_id']
            user = existing_email
        else:
            # Create new user
            username = user_info['name'] or user_info['email'].split('@')[0]
            # Ensure unique username
            base_username = username
            counter = 1
            while db.query(User).filter(User.username == username).first():
                username = f"{base_username}{counter}"
                counter += 1
            
            user = User(
                username=username,
                email=user_info['email'],
                oauth_provider='google',
                oauth_id=user_info['oauth_id']
            )
            db.add(user)
    
    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    # Generate tokens and redirect to frontend with token
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    # Redirect to frontend with tokens in URL fragment (more secure than query params)
    return RedirectResponse(
        url=f"/?access_token={access_token}&refresh_token={refresh_token}"
    )


@router.get("/facebook")
async def facebook_auth(request: Request):
    """Redirect to Facebook OAuth."""
    if not config.is_facebook_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Facebook OAuth not configured"
        )
    redirect = await oauth_module.get_oauth_authorize_redirect('facebook', request)
    return redirect


@router.get("/facebook/callback")
async def facebook_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Facebook OAuth callback."""
    user_info = await oauth_module.get_facebook_user_info(request)
    
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Facebook authentication failed"
        )
    
    # Find or create user (similar logic to Google)
    user = db.query(User).filter(
        User.oauth_provider == 'facebook',
        User.oauth_id == user_info['oauth_id']
    ).first()
    
    if not user:
        existing_email = db.query(User).filter(User.email == user_info['email']).first()
        if existing_email:
            existing_email.oauth_provider = 'facebook'
            existing_email.oauth_id = user_info['oauth_id']
            user = existing_email
        else:
            username = user_info['name'] or user_info['email'].split('@')[0]
            base_username = username
            counter = 1
            while db.query(User).filter(User.username == username).first():
                username = f"{base_username}{counter}"
                counter += 1
            
            user = User(
                username=username,
                email=user_info['email'],
                oauth_provider='facebook',
                oauth_id=user_info['oauth_id']
            )
            db.add(user)
    
    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return RedirectResponse(
        url=f"/?access_token={access_token}&refresh_token={refresh_token}"
    )


@router.get("/apple")
async def apple_auth(request: Request):
    """Redirect to Apple OAuth."""
    if not config.is_apple_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Apple OAuth not configured"
        )
    redirect = await oauth_module.get_oauth_authorize_redirect('apple', request)
    return redirect


@router.post("/apple/callback")
async def apple_callback(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle Apple OAuth callback.
    Apple uses POST with form data.
    """
    form_data = await request.form()
    id_token = form_data.get('id_token')
    code = form_data.get('code')
    
    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No id_token received from Apple"
        )
    
    user_info = await oauth_module.get_apple_user_info(id_token, code)
    
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Apple authentication failed"
        )
    
    # Find or create user
    user = db.query(User).filter(
        User.oauth_provider == 'apple',
        User.oauth_id == user_info['oauth_id']
    ).first()
    
    if not user:
        existing_email = db.query(User).filter(User.email == user_info['email']).first()
        if existing_email:
            existing_email.oauth_provider = 'apple'
            existing_email.oauth_id = user_info['oauth_id']
            user = existing_email
        else:
            # Apple might not provide name, use email prefix
            username = user_info['email'].split('@')[0] if user_info['email'] else f"apple_user_{user_info['oauth_id'][:8]}"
            base_username = username
            counter = 1
            while db.query(User).filter(User.username == username).first():
                username = f"{base_username}{counter}"
                counter += 1
            
            user = User(
                username=username,
                email=user_info['email'],
                oauth_provider='apple',
                oauth_id=user_info['oauth_id']
            )
            db.add(user)
    
    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return RedirectResponse(
        url=f"/?access_token={access_token}&refresh_token={refresh_token}"
    )


# =====================
# OAuth Status
# =====================

@router.get("/providers")
def get_oauth_providers():
    """Get available OAuth providers status."""
    return {
        "google": config.is_google_configured(),
        "facebook": config.is_facebook_configured(),
        "apple": config.is_apple_configured()
    }
