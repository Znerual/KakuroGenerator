"""
Test script for email verification system.
Run this to test your Resend configuration without starting the full app.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python import config
from python.email_service import send_verification_email, send_password_reset_email, send_welcome_email


def test_resend_config():
    """Test if Resend is properly configured."""
    print("=" * 60)
    print("RESEND CONFIGURATION TEST")
    print("=" * 60)
    
    print(f"\nAPP_HOST: {config.APP_HOST}")
    print(f"RESEND_API_KEY: {'✓ Set' if config.RESEND_API_KEY else '✗ Not set'}")
    print(f"RESEND_FROM_EMAIL: {config.RESEND_FROM_EMAIL}")
    print(f"Resend Configured: {config.is_resend_configured()}")
    
    if not config.is_resend_configured():
        print("\n⚠️  RESEND IS NOT CONFIGURED!")
        print("Please set RESEND_API_KEY in your .env file.")
        print("Get your API key from: https://resend.com/api-keys")
        return False
    
    return True


def test_send_emails(recipient_email):
    """Test sending all email types."""
    
    if not test_resend_config():
        return
    
    print("\n" + "=" * 60)
    print("SENDING TEST EMAILS")
    print("=" * 60)
    print(f"\nRecipient: {recipient_email}")
    
    # Test verification email
    print("\n1. Testing Verification Email...")
    test_token = "test_verification_token_123456"
    success = send_verification_email(recipient_email, test_token, "Test User")
    print(f"   Result: {'✓ Success' if success else '✗ Failed'}")
    
    # Test password reset email
    print("\n2. Testing Password Reset Email...")
    reset_token = "test_reset_token_123456"
    success = send_password_reset_email(recipient_email, reset_token, "Test User")
    print(f"   Result: {'✓ Success' if success else '✗ Failed'}")
    
    # Test welcome email
    print("\n3. Testing Welcome Email...")
    success = send_welcome_email(recipient_email, "Test User")
    print(f"   Result: {'✓ Success' if success else '✗ Failed'}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print("\nCheck your email inbox (and spam folder) for the test emails.")
    print("Note: In development mode, emails only go to your Resend account email.")


if __name__ == "__main__":
    print("\n🧪 Email Verification System Test\n")
    
    if len(sys.argv) > 1:
        recipient = sys.argv[1]
    else:
        recipient = input("Enter email address to send test emails to: ").strip()
    
    if not recipient:
        print("Error: No email address provided")
        sys.exit(1)
    
    # Validate email format (basic check)
    if "@" not in recipient or "." not in recipient:
        print("Error: Invalid email address format")
        sys.exit(1)
    
    test_send_emails(recipient)
    
    print("\n💡 Tips:")
    print("  - If emails aren't arriving, check your Resend dashboard")
    print("  - View logs at: https://resend.com/emails")
    print("  - In development, only your registered email receives test emails")
    print("  - For production, verify your domain at: https://resend.com/domains")