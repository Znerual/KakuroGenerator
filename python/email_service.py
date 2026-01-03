"""
Email service for sending verification and password reset emails.
Uses Resend API for email delivery.
"""

import resend
from typing import Optional
import kakuro.config as config


def send_verification_email(email: str, code: str, user_name: Optional[str] = None) -> bool:
    """
    Send email verification link to user.
    
    Args:
        email: User's email address
        code: Verification code
        user_name: Optional user name for personalization
        
    Returns:
        True if email sent successfully, False otherwise
    """
    if not config.is_resend_configured():
        print("Resend not configured, skipping email")
        return False
    
    resend.api_key = config.RESEND_API_KEY
    
    greeting = f"Hi {user_name}," if user_name else "Hi,"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .code {{ 
                font-size: 32px; 
                font-weight: bold; 
                letter-spacing: 5px; 
                color: #4CAF50; 
                background: #f4f4f4; 
                padding: 15px; 
                text-align: center; 
                border-radius: 8px; 
                margin: 20px 0;
            }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Verify Your Email Address</h2>
            <p>{greeting}</p>
            <p>Thank you for registering with Kakuro Generator! Please use the following code to complete your registration:</p>
            
            <div class="code">{code}</div>
            
            <p>This code will expire in 15 minutes.</p>
            <div class="footer">
                <p>If you didn't create an account, you can safely ignore this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    try:
        params = {
            "from": config.RESEND_FROM_EMAIL,
            "to": [email],
            "subject": f"Your Verification Code: {code}",
            "html": html_content,
        }
        
        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"Error sending verification email: {e}")
        return False


def send_password_reset_email(email: str, token: str, user_name: Optional[str] = None) -> bool:
    """
    Send password reset link to user.
    
    Args:
        email: User's email address
        token: Password reset token
        user_name: Optional user name for personalization
        
    Returns:
        True if email sent successfully, False otherwise
    """
    if not config.is_resend_configured():
        print("Resend not configured, skipping email")
        return False
    
    resend.api_key = config.RESEND_API_KEY
    
    reset_url = f"{config.APP_HOST}/reset-password?token={token}"
    
    greeting = f"Hi {user_name}," if user_name else "Hi,"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .button {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #2196F3;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                margin: 20px 0;
            }}
            .warning {{
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                padding: 10px;
                border-radius: 4px;
                margin: 20px 0;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                font-size: 12px;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Reset Your Password</h2>
            <p>{greeting}</p>
            <p>We received a request to reset your password for your Kakuro Generator account.</p>
            <p>
                <a href="{reset_url}" class="button">Reset Password</a>
            </p>
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #666;">{reset_url}</p>
            <div class="warning">
                <strong>⚠️ Security Notice:</strong> This password reset link will expire in 1 hour.
            </div>
            <div class="footer">
                <p>If you didn't request a password reset, please ignore this email. Your password will remain unchanged.</p>
                <p>For security reasons, never share this link with anyone.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    try:
        params = {
            "from": config.RESEND_FROM_EMAIL,
            "to": [email],
            "subject": "Reset Your Password - Kakuro Generator",
            "html": html_content,
        }
        
        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return False


def send_welcome_email(email: str, user_name: Optional[str] = None) -> bool:
    """
    Send welcome email after successful verification.
    
    Args:
        email: User's email address
        user_name: Optional user name for personalization
        
    Returns:
        True if email sent successfully, False otherwise
    """
    if not config.is_resend_configured():
        return False
    
    resend.api_key = config.RESEND_API_KEY
    
    greeting = f"Hi {user_name}," if user_name else "Hi,"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .button {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #4CAF50;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                margin: 20px 0;
            }}
            .features {{
                background-color: #f5f5f5;
                padding: 15px;
                border-radius: 4px;
                margin: 20px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Welcome to Kakuro Generator! 🎉</h2>
            <p>{greeting}</p>
            <p>Your email has been verified successfully! You're all set to start enjoying Kakuro puzzles.</p>
            <div class="features">
                <h3>What you can do now:</h3>
                <ul>
                    <li>Generate unlimited Kakuro puzzles</li>
                    <li>Save your progress across devices</li>
                    <li>Track your solved puzzles</li>
                    <li>Choose from multiple difficulty levels</li>
                </ul>
            </div>
            <p>
                <a href="{config.APP_HOST}" class="button">Start Playing</a>
            </p>
            <p>Happy puzzling!</p>
        </div>
    </body>
    </html>
    """
    
    try:
        params = {
            "from": config.RESEND_FROM_EMAIL,
            "to": [email],
            "subject": "Welcome to Kakuro Generator! 🎉",
            "html": html_content,
        }
        
        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"Error sending welcome email: {e}")
        return False