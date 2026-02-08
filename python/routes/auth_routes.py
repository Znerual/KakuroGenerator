"""
Authentication routes for Kakuro Generator.
Handles registration, login, OAuth, email verification, and password reset.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
import uuid
from datetime import datetime, timezone, timedelta

from python.database import get_db
from python.models import User
from python.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    generate_verification_code,
    create_password_reset_token,
    verify_password_reset_token,
    get_current_user,
    get_current_user_and_session,
    get_required_user,
)
from python.oauth import (
    get_oauth_authorize_redirect,
    get_google_user_info,
    get_facebook_user_info,
    get_apple_user_info
)
from python.email_service import (
    send_verification_email,
    send_password_reset_email,
    send_welcome_email
)
from python.analytics import start_user_session, end_user_session
from python.performance import log_auth_attempt, Timer
import python.config as config

router = APIRouter(prefix="/auth", tags=["authentication"])

limiter = Limiter(key_func=get_remote_address)


# Request/Response Models
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    username: Optional[str] = None
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class MessageResponse(BaseModel):
    message: str


# Registration Endpoints
@router.post("/register", response_model=MessageResponse)
@limiter.limit("5/minute")
async def register(register_data: RegisterRequest, request: Request,  background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Register a new user with email and password.
    Sends verification code via email.
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == register_data.email).first()
    if existing_user:
        if not existing_user.email_verified:
            # User exists but is not verified -> Prompt for verification
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account exists but is not verified. Please check your email for the code."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Check username uniqueness if provided
    if register_data.username:
        existing_username = db.query(User).filter(User.username == register_data.username).first()
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
    
    # Generate verification code
    verification_code = generate_verification_code()
    # Use config hours or default to 15 minutes if not set in config for codes
    expire_hours = getattr(config, 'EMAIL_VERIFICATION_EXPIRE_HOURS', 0.25)
    code_expires = datetime.now(timezone.utc) + timedelta(hours=expire_hours)
    
    # Create new user
    user_id = str(uuid.uuid4())
    new_user = User(
        id=user_id,
        email=register_data.email,
        username=register_data.username,
        password_hash=hash_password(register_data.password),
        full_name=register_data.full_name,
        email_verified=False,
        verification_code=verification_code,
        verification_code_expires_at=code_expires
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Log registration
    log_auth_attempt(db, register_data.email, "REGISTER", "SUCCESS", request, user_id=user_id)
    
    # Send verification email
    if config.is_resend_configured():
        background_tasks.add_task(send_verification_email, register_data.email, verification_code, register_data.full_name or register_data.username)
        return {"message": "Registration successful! Please check your email for a verification code."}
    else:
        # If email not configured, print code to console for dev ONLY IF DEBUG IS ON
        if config.DEBUG:
            print(f"DEV MODE: Verification code for {register_data.email} is {verification_code}")
            return {"message": f"DEV MODE: Verification code is {verification_code}"}
        else:
            return {"message": "Verification code sent (Dev mode hidden)"}



@router.post("/login", response_model=AuthResponse)
@limiter.limit("5/minute")
async def login(login_data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Login with email and password.
    Returns access and refresh tokens.
    """
    # Find user
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Verify password
    if not verify_password(login_data.password, user.password_hash):
        log_auth_attempt(db, login_data.email, "LOGIN", "FAILURE", request, user_id=user.id, reason="Invalid password")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Check if email is verified
    if not user.email_verified:
        log_auth_attempt(db, login_data.email, "LOGIN", "FAILURE", request, user_id=user.id, reason="Email not verified")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before logging in. Check your inbox for the verification link."
        )
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)

    # --- ANALYTICS START ---
    # Determine device type from user agent (simple heuristic)
    ua = request.headers.get("user-agent", "").lower()
    device_type = "mobile" if "mobile" in ua else "desktop"
    
    # Create Database Session Record
    session = start_user_session(db, user.id, request, device_type)
    # --- ANALYTICS END ---
    
    db.commit()
    
    # Log successful login
    log_auth_attempt(db, login_data.email, "LOGIN", "SUCCESS", request, user_id=user.id)
    
    # Generate tokens
    access_token = create_access_token(user.id, session.id)
    refresh_token = create_refresh_token(user.id, session.id)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user.to_dict()
    }

@router.post("/logout", response_model=MessageResponse)
async def logout(
    auth_data: tuple[Optional[User], Optional[str]] = Depends(get_current_user_and_session),
    db: Session = Depends(get_db)
):
    """
    Logs out the user by marking the session as ended in the database.
    """
    user, session_id = auth_data
    if session_id:
        end_user_session(db, session_id)
    
    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=AuthResponse)
async def refresh_access_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    Refresh access token using refresh token.
    """
    from python.auth import decode_token
    
    # Decode refresh token
    payload = decode_token(request.refresh_token, expected_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    user_id = payload.get("sub")
    session_id = payload.get("sid")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Find user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Generate new tokens
    new_access_token = create_access_token(user.id, session_id)
    new_refresh_token = create_refresh_token(user.id, session_id)
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "user": user.to_dict()
    }


# Email Verification Endpoints
@router.post("/verify-email", response_model=AuthResponse)
@limiter.limit("5/minute")
async def verify_email(
    request_data: VerifyEmailRequest, 
    request: Request, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Verify user's email address using the 6-digit code.
    """
    # 1. Find user by email
    user = db.query(User).filter(User.email == request_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # 2. Check if already verified
    if user.email_verified:
        # If already verified, we can just log them in again
        pass 
    else:
        # 3. Validate Code
        if not user.verification_code or user.verification_code != request_data.code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code"
            )
        
        # 4. Check Expiration
        now = datetime.now(timezone.utc)
        expires_at = user.verification_code_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at and expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code has expired. Please request a new one."
            )
        
        # 5. Success - Mark verified and clear code
        user.email_verified = True
        user.verification_code = None
        user.verification_code_expires_at = None
        
        # Send welcome email
        if config.is_resend_configured():
            background_tasks.add_task(send_welcome_email, user.email, user.full_name or user.username)
        
    # 6. Auto-Login Logic (Create Session)
    user.last_login = datetime.now(timezone.utc)
    
    ua = request.headers.get("user-agent", "").lower()
    device_type = "mobile" if "mobile" in ua else "desktop"
    session = start_user_session(db, user.id, request, device_type)

    # Log verification login
    log_auth_attempt(db, user.email, "EMAIL_VERIFICATION_LOGIN", "SUCCESS", request, user_id=user.id)

    db.commit()
    # 6. Generate Tokens (Auto-Login)
    access_token = create_access_token(user.id, session.id)
    refresh_token = create_refresh_token(user.id, session.id)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user.to_dict()
    }

@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("5/minute")
async def resend_verification(request: ResendVerificationRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Resend verification code to user.
    """
    # Find user
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        # Don't reveal if email exists (security best practice)
        log_auth_attempt(db, request.email, "RESEND_VERIFICATION", "FAILURE", request, reason="User not found")
        return {"message": "If an account exists with this email, a verification code has been sent."}
    
    # Check if already verified
    if user.email_verified:
        log_auth_attempt(db, request.email, "RESEND_VERIFICATION", "FAILURE", request, reason="Email already verified")
        return {"message": "This email is already verified. You can log in now."}
    
    # Generate new verification code
    expire_hours = getattr(config, 'EMAIL_VERIFICATION_EXPIRE_HOURS', 1.0)

    current_expires_at = user.verification_code_expires_at
    if current_expires_at.tzinfo is None:
        current_expires_at = current_expires_at.replace(tzinfo=timezone.utc)


    # The time the current code was created is (Expires - Lifetime)
    # Using timedelta to reverse check
    created_at = current_expires_at - timedelta(hours=expire_hours)
    
    # If the code was created less than 60 seconds ago, block the request
    if (now - created_at).total_seconds() < 60:
        log_auth_attempt(db, request.email, "RESEND_VERIFICATION", "FAILURE", request, reason="Too many requests")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait 60 seconds before requesting a new code."
        )
    
    verification_code = generate_verification_code()
    code_expires = datetime.now(timezone.utc) + timedelta(hours=expire_hours)
    
    user.verification_code = verification_code
    user.verification_code_expires_at = code_expires
    db.commit()
    
    # Send verification email
    if config.is_resend_configured():
        log_auth_attempt(db, request.email, "RESEND_VERIFICATION", "SUCCESS", request, reason="Verification code resent")
        background_tasks.add_task(send_verification_email, user.email, verification_code, user.full_name or user.username)
    else:
        log_auth_attempt(db, request.email, "RESEND_VERIFICATION", "FAILURE", request, reason="Email service not configured")
        if config.DEBUG:
            print(f"DEV MODE: Resent verification code for {user.email}: {verification_code}")
    
    return {"message": "If an account exists with this email, a verification code has been sent."}

# Password Reset Endpoints
@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def forgot_password(request_data: ForgotPasswordRequest, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Request a password reset link.
    """
    # Find user
    user = db.query(User).filter(User.email == request_data.email).first()
    
    # Always return success message (don't reveal if email exists)
    if not user or not user.password_hash:  # OAuth users can't reset password this way
        log_auth_attempt(db, request_data.email, "FORGOT_PASSWORD", "FAILURE", request, reason="User not found or no password")
        return {"message": "If an account exists with this email, a password reset link has been sent."}
    
    # Send password reset email
    reset_token = create_password_reset_token(user.id, user.email)
    if config.is_resend_configured():
        background_tasks.add_task(send_password_reset_email, user.email, reset_token, user.full_name or user.username)
        log_auth_attempt(db, request_data.email, "FORGOT_PASSWORD", "SUCCESS", request, reason="Password reset email sent")
    else:
        log_auth_attempt(db, request_data.email, "FORGOT_PASSWORD", "FAILURE", request, reason="Email service not configured")
        print(f"DEV MODE: Password reset email with link: {config.APP_HOST}/reset-password?token={reset_token}")

    
    return {"message": "If an account exists with this email, a password reset link has been sent."}


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(request_data: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """
    Reset password using the token from the reset email.
    """
    # Verify token
    token_data = verify_password_reset_token(request_data.token)
    if not token_data:
        log_auth_attempt(db, request_data.email, "RESET_PASSWORD", "FAILURE", request, reason="Invalid or expired reset token")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Find user
    user = db.query(User).filter(User.id == token_data["user_id"]).first()
    if not user or not user.password_hash:
        log_auth_attempt(db, request_data.email, "RESET_PASSWORD", "FAILURE", request, reason="User not found or cannot reset password")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or cannot reset password"
        )
    
    # Update password
    user.password_hash = hash_password(request_data.new_password)
    db.commit()
    
    log_auth_attempt(db, user.email, "RESET_PASSWORD", "SUCCESS", request, reason="Password reset successful")
    return {"message": "Password reset successful! You can now log in with your new password."}


# OAuth Endpoints
@router.get("/oauth/{provider}")
async def oauth_login(provider: str, request: Request):
    """
    Initiate OAuth login flow for Google, Facebook, or Apple.
    """
    redirect_response = get_oauth_authorize_redirect(provider, request)
    if not redirect_response:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth provider '{provider}' not configured or invalid"
        )
    return redirect_response


@router.get("/google/callback", response_model=AuthResponse)
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Google OAuth callback."""
    user_info = await get_google_user_info(request)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to get user info from Google"
        )
    
    return await handle_oauth_user(user_info, db, request)


@router.get("/facebook/callback", response_model=AuthResponse)
async def facebook_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Facebook OAuth callback."""
    user_info = await get_facebook_user_info(request)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to get user info from Facebook"
        )
    
    return await handle_oauth_user(user_info, db, request)


@router.post("/apple/callback", response_model=AuthResponse)
async def apple_callback(
    id_token: str,
    code: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Apple Sign In callback."""
    user_info = await get_apple_user_info(id_token, code)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to get user info from Apple"
        )
    
    return await handle_oauth_user(user_info, db, request)


async def handle_oauth_user(user_info: dict, db: Session, request: Request) -> AuthResponse:
    """
    Handle OAuth user creation or login.
    OAuth users are automatically verified.
    """
    provider = user_info['provider']
    oauth_id = user_info['oauth_id']
    email = user_info['email']
    
    # Try to find existing user by OAuth ID
    user = db.query(User).filter(
        User.oauth_provider == provider,
        User.oauth_id == oauth_id
    ).first()
    
    if not user:
        # Try to find by email
        user = db.query(User).filter(User.email == email).first()
        if user:
            # Link OAuth account to existing user
            user.oauth_provider = provider
            user.oauth_id = oauth_id
            user.email_verified = True  # OAuth emails are pre-verified
        else:
            # Create new user
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                username=None,  # Can be set later
                full_name=user_info.get('name'),
                oauth_provider=provider,
                oauth_id=oauth_id,
                email_verified=True  # OAuth emails are pre-verified
            )
            db.add(user)
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)

    ua = request.headers.get("user-agent", "").lower()
    device_type = "mobile" if "mobile" in ua else "desktop"
    session = start_user_session(db, user.id, request, device_type)
    
    db.commit()
    db.refresh(user)

    # Log successful OAuth login
    log_auth_attempt(db, email, f"{provider.upper()}_LOGIN", "SUCCESS", request, user_id=user.id)
    
    # Generate tokens
    access_token = create_access_token(user.id, session.id)
    refresh_token = create_refresh_token(user.id, session.id)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user.to_dict()
    }


# User Info Endpoints
@router.get("/me")
async def get_me(current_user: User = Depends(get_required_user)):
    """Get current user's profile."""
    return current_user.to_dict()


@router.get("/check")
async def check_auth(current_user: Optional[User] = Depends(get_current_user)):
    """Check if user is authenticated (optional dependency)."""
    if current_user:
        return {
            "authenticated": True,
            "user": current_user.to_dict()
        }
    return {"authenticated": False}