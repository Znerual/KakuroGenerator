"""
Test script for authentication endpoints.
Run with: python test_auth.py
"""

import httpx
import json

BASE_URL = "http://localhost:8008"


def test_register():
    """Test user registration."""
    print("\n=== Testing Registration ===")
    response = httpx.post(
        f"{BASE_URL}/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123"
        }
    )
    print(f"Status: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response text: {response.text}")
    return response.json() if response.status_code == 200 else None


def test_duplicate_register():
    """Test registration with duplicate email."""
    print("\n=== Testing Duplicate Registration ===")
    response = httpx.post(
        f"{BASE_URL}/auth/register",
        json={
            "username": "testuser2",
            "email": "test@example.com",
            "password": "testpass123"
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 400  # Should fail


def test_login(email, password):
    """Test user login."""
    print("\n=== Testing Login ===")
    response = httpx.post(
        f"{BASE_URL}/auth/login",
        json={
            "email": email,
            "password": password
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.json() if response.status_code == 200 else None


def test_wrong_password():
    """Test login with wrong password."""
    print("\n=== Testing Wrong Password ===")
    response = httpx.post(
        f"{BASE_URL}/auth/login",
        json={
            "email": "test@example.com",
            "password": "wrongpassword"
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 401  # Should fail


def test_profile(access_token):
    """Test getting user profile."""
    print("\n=== Testing Profile ===")
    response = httpx.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200


def test_refresh_token(refresh_token):
    """Test token refresh."""
    print("\n=== Testing Token Refresh ===")
    response = httpx.post(
        f"{BASE_URL}/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.json() if response.status_code == 200 else None


def test_oauth_providers():
    """Test OAuth providers status."""
    print("\n=== Testing OAuth Providers Status ===")
    response = httpx.get(f"{BASE_URL}/auth/providers")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200


def main():
    print("=" * 50)
    print("Authentication API Tests")
    print("=" * 50)
    
    # Test OAuth providers status
    test_oauth_providers()
    
    # Test registration
    tokens = test_register()
    
    if tokens:
        # Test duplicate registration
        test_duplicate_register()
        
        # Test wrong password
        test_wrong_password()
        
        # Test login
        login_tokens = test_login("test@example.com", "testpass123")
        
        if login_tokens:
            # Test profile
            test_profile(login_tokens["access_token"])
            
            # Test token refresh
            test_refresh_token(login_tokens["refresh_token"])
    
    print("\n" + "=" * 50)
    print("Tests completed!")
    print("=" * 50)


if __name__ == "__main__":
    main()
