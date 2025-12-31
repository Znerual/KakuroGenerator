"""
Debug script to check email configuration and test registration flow.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_config():
    """Check if email configuration is set up."""
    print("=" * 60)
    print("CONFIGURATION CHECK")
    print("=" * 60)
    
    # Check environment variables
    resend_api_key = os.getenv("RESEND_API_KEY")
    resend_from_email = os.getenv("RESEND_FROM_EMAIL")
    
    print(f"\n1. Environment Variables:")
    print(f"   RESEND_API_KEY: {'✓ Set' if resend_api_key else '✗ NOT SET'}")
    if resend_api_key:
        print(f"      Value: {resend_api_key[:10]}..." if len(resend_api_key) > 10 else f"      Value: {resend_api_key}")
    print(f"   RESEND_FROM_EMAIL: {resend_from_email or '✗ NOT SET'}")
    
    # Try importing config
    try:
        import python.config as config
        print(f"\n2. Python Config Module:")
        print(f"   is_resend_configured(): {config.is_resend_configured()}")
        print(f"   RESEND_API_KEY: {'✓ Set' if config.RESEND_API_KEY else '✗ NOT SET'}")
        print(f"   RESEND_FROM_EMAIL: {config.RESEND_FROM_EMAIL}")
        print(f"   EMAIL_VERIFICATION_EXPIRE_HOURS: {config.EMAIL_VERIFICATION_EXPIRE_HOURS}")
    except Exception as e:
        print(f"\n2. Python Config Module: ✗ FAILED TO LOAD")
        print(f"   Error: {e}")
        return False
    
    # Try importing email service
    try:
        from python.email_service import send_verification_email
        print(f"\n3. Email Service Module: ✓ Loaded")
    except Exception as e:
        print(f"\n3. Email Service Module: ✗ FAILED TO LOAD")
        print(f"   Error: {e}")
        return False
    
    # Try importing auth module
    try:
        from python.auth import generate_verification_code
        test_code = generate_verification_code()
        print(f"\n4. Auth Module: ✓ Loaded")
        print(f"   Test code generated: {test_code}")
    except Exception as e:
        print(f"\n4. Auth Module: ✗ FAILED TO LOAD")
        print(f"   Error: {e}")
        return False
    
    # Check .env file
    env_file = ".env"
    if os.path.exists(env_file):
        print(f"\n5. .env File: ✓ Found at {os.path.abspath(env_file)}")
        with open(env_file, 'r') as f:
            lines = f.readlines()
            resend_lines = [l.strip() for l in lines if 'RESEND' in l and not l.strip().startswith('#')]
            if resend_lines:
                print("   Resend configuration lines:")
                for line in resend_lines:
                    # Mask the API key
                    if 'RESEND_API_KEY' in line and '=' in line:
                        key, val = line.split('=', 1)
                        val = val.strip()
                        if val and len(val) > 10:
                            print(f"      {key}={val[:10]}...{val[-4:]}")
                        else:
                            print(f"      {line}")
                    else:
                        print(f"      {line}")
            else:
                print("   ✗ No RESEND configuration found in .env")
    else:
        print(f"\n5. .env File: ✗ NOT FOUND")
        print(f"   Expected location: {os.path.abspath(env_file)}")
        print("   Please create .env file with RESEND_API_KEY")
    
    print("\n" + "=" * 60)
    
    if not config.is_resend_configured():
        print("\n⚠️  EMAIL NOT CONFIGURED!")
        print("\nTo fix:")
        print("1. Sign up at https://resend.com/signup")
        print("2. Get your API key from https://resend.com/api-keys")
        print("3. Create/edit .env file with:")
        print("   RESEND_API_KEY=re_your_api_key_here")
        print("   RESEND_FROM_EMAIL=Kakuro Generator <onboarding@resend.dev>")
        print("\n4. Restart your application")
        return False
    else:
        print("\n✓ EMAIL IS CONFIGURED!")
        print("\nYou can now:")
        print("- Register new users")
        print("- Send verification codes")
        print("- Test with: python test_email.py your-email@example.com")
        return True


if __name__ == "__main__":
    # Load .env if python-dotenv is available
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("Loaded environment from .env file\n")
    except ImportError:
        print("python-dotenv not installed, using system environment only\n")
    
    success = check_config()
    sys.exit(0 if success else 1)