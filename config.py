"""
Configuration settings for Kakuro Generator.
Manages secrets, OAuth credentials, and application settings.
"""

import os
import secrets
from typing import Optional

# JWT Configuration
# In production, set JWT_SECRET_KEY environment variable
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# OAuth Configuration
# Set these environment variables with your OAuth app credentials

# Google OAuth
GOOGLE_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")

# Facebook OAuth
FACEBOOK_CLIENT_ID: Optional[str] = os.getenv("FACEBOOK_CLIENT_ID")
FACEBOOK_CLIENT_SECRET: Optional[str] = os.getenv("FACEBOOK_CLIENT_SECRET")

# Apple OAuth
APPLE_CLIENT_ID: Optional[str] = os.getenv("APPLE_CLIENT_ID")  # Service ID
APPLE_TEAM_ID: Optional[str] = os.getenv("APPLE_TEAM_ID")
APPLE_KEY_ID: Optional[str] = os.getenv("APPLE_KEY_ID")
APPLE_PRIVATE_KEY: Optional[str] = os.getenv("APPLE_PRIVATE_KEY")  # Contents of .p8 file

# Application settings
APP_HOST = os.getenv("APP_HOST", "http://localhost:8008")

# OAuth redirect URIs (constructed from APP_HOST)
GOOGLE_REDIRECT_URI = f"{APP_HOST}/auth/google/callback"
FACEBOOK_REDIRECT_URI = f"{APP_HOST}/auth/facebook/callback"
APPLE_REDIRECT_URI = f"{APP_HOST}/auth/apple/callback"


def is_google_configured() -> bool:
    """Check if Google OAuth is properly configured."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def is_facebook_configured() -> bool:
    """Check if Facebook OAuth is properly configured."""
    return bool(FACEBOOK_CLIENT_ID and FACEBOOK_CLIENT_SECRET)


def is_apple_configured() -> bool:
    """Check if Apple OAuth is properly configured."""
    return bool(APPLE_CLIENT_ID and APPLE_TEAM_ID and APPLE_KEY_ID and APPLE_PRIVATE_KEY)
