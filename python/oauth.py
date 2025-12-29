"""
OAuth configuration for Google, Facebook, and Apple authentication.
Uses Authlib for OAuth 2.0 client implementation.
"""

from typing import Optional, Dict, Any
from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request
import httpx
import jwt as pyjwt  # For Apple JWT verification
from datetime import datetime, timedelta

import python.config as config

# Initialize OAuth client
oauth = OAuth()

# Register Google OAuth client
if config.is_google_configured():
    oauth.register(
        name='google',
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

# Register Facebook OAuth client
if config.is_facebook_configured():
    oauth.register(
        name='facebook',
        client_id=config.FACEBOOK_CLIENT_ID,
        client_secret=config.FACEBOOK_CLIENT_SECRET,
        authorize_url='https://www.facebook.com/v18.0/dialog/oauth',
        access_token_url='https://graph.facebook.com/v18.0/oauth/access_token',
        api_base_url='https://graph.facebook.com/v18.0/',
        client_kwargs={
            'scope': 'email public_profile'
        }
    )


async def get_google_user_info(request: Request) -> Optional[Dict[str, Any]]:
    """
    Handle Google OAuth callback and get user info.
    
    Returns:
        Dictionary with 'email', 'name', 'sub' (Google user ID)
        or None if authentication failed.
    """
    if not config.is_google_configured():
        return None
    
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if user_info:
            return {
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'oauth_id': user_info.get('sub'),
                'provider': 'google'
            }
    except Exception as e:
        print(f"Google OAuth error: {e}")
    return None


async def get_facebook_user_info(request: Request) -> Optional[Dict[str, Any]]:
    """
    Handle Facebook OAuth callback and get user info.
    
    Returns:
        Dictionary with 'email', 'name', 'id' (Facebook user ID)
        or None if authentication failed.
    """
    if not config.is_facebook_configured():
        return None
    
    try:
        token = await oauth.facebook.authorize_access_token(request)
        access_token = token.get('access_token')
        
        # Fetch user info from Facebook Graph API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'https://graph.facebook.com/v18.0/me',
                params={
                    'fields': 'id,name,email',
                    'access_token': access_token
                }
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'email': data.get('email'),
                    'name': data.get('name'),
                    'oauth_id': data.get('id'),
                    'provider': 'facebook'
                }
    except Exception as e:
        print(f"Facebook OAuth error: {e}")
    return None


def generate_apple_client_secret() -> str:
    """
    Generate the client secret for Apple Sign In.
    Apple requires a JWT signed with your private key as the client secret.
    """
    if not config.is_apple_configured():
        raise ValueError("Apple OAuth not configured")
    
    now = datetime.utcnow()
    payload = {
        'iss': config.APPLE_TEAM_ID,
        'iat': now,
        'exp': now + timedelta(days=180),
        'aud': 'https://appleid.apple.com',
        'sub': config.APPLE_CLIENT_ID
    }
    
    headers = {
        'kid': config.APPLE_KEY_ID,
        'alg': 'ES256'
    }
    
    return pyjwt.encode(
        payload,
        config.APPLE_PRIVATE_KEY,
        algorithm='ES256',
        headers=headers
    )


async def get_apple_user_info(id_token: str, code: str) -> Optional[Dict[str, Any]]:
    """
    Handle Apple Sign In callback and get user info.
    Apple sends an id_token that contains user info.
    
    Args:
        id_token: The JWT id_token from Apple
        code: The authorization code from Apple
        
    Returns:
        Dictionary with 'email', 'sub' (Apple user ID)
        or None if authentication failed.
    """
    if not config.is_apple_configured():
        return None
    
    try:
        # For Apple, we need to verify the id_token
        # In production, you should fetch Apple's public keys and verify properly
        # For now, we decode without verification (NOT RECOMMENDED for production)
        claims = pyjwt.decode(id_token, options={"verify_signature": False})
        
        return {
            'email': claims.get('email'),
            'name': None,  # Apple only sends name on first authorization
            'oauth_id': claims.get('sub'),
            'provider': 'apple'
        }
    except Exception as e:
        print(f"Apple OAuth error: {e}")
    return None


def get_oauth_authorize_redirect(provider: str, request: Request):
    """
    Get the OAuth authorization redirect for a provider.
    
    Args:
        provider: 'google', 'facebook', or 'apple'
        request: The Starlette/FastAPI request object
        
    Returns:
        RedirectResponse to the OAuth provider's authorization page
    """
    redirect_uri_map = {
        'google': config.GOOGLE_REDIRECT_URI,
        'facebook': config.FACEBOOK_REDIRECT_URI,
        'apple': config.APPLE_REDIRECT_URI
    }
    
    redirect_uri = redirect_uri_map.get(provider)
    
    if provider == 'google' and config.is_google_configured():
        return oauth.google.authorize_redirect(request, redirect_uri)
    elif provider == 'facebook' and config.is_facebook_configured():
        return oauth.facebook.authorize_redirect(request, redirect_uri)
    elif provider == 'apple' and config.is_apple_configured():
        # Apple uses a special flow
        # For simplicity, redirect to Apple's authorization page
        from urllib.parse import urlencode
        params = {
            'client_id': config.APPLE_CLIENT_ID,
            'redirect_uri': redirect_uri,
            'response_type': 'code id_token',
            'scope': 'email name',
            'response_mode': 'form_post'
        }
        auth_url = f"https://appleid.apple.com/auth/authorize?{urlencode(params)}"
        from starlette.responses import RedirectResponse
        return RedirectResponse(url=auth_url)
    
    return None
