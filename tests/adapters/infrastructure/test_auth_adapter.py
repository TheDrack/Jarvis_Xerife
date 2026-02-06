# -*- coding: utf-8 -*-
"""Tests for AuthAdapter"""

import pytest
from jose import jwt

from app.adapters.infrastructure.auth_adapter import AuthAdapter
from app.core.config import settings


@pytest.fixture
def auth_adapter():
    """Create an AuthAdapter instance for testing"""
    return AuthAdapter()


class TestPasswordHashing:
    """Tests for password hashing functionality"""

    def test_hash_password(self, auth_adapter):
        """Test password hashing"""
        password = "test_password_123"
        hashed = auth_adapter.get_password_hash(password)
        
        assert hashed is not None
        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt hash prefix

    def test_verify_correct_password(self, auth_adapter):
        """Test verifying correct password"""
        password = "test_password_123"
        hashed = auth_adapter.get_password_hash(password)
        
        assert auth_adapter.verify_password(password, hashed) is True

    def test_verify_incorrect_password(self, auth_adapter):
        """Test verifying incorrect password"""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = auth_adapter.get_password_hash(password)
        
        assert auth_adapter.verify_password(wrong_password, hashed) is False

    def test_different_hashes_for_same_password(self, auth_adapter):
        """Test that same password produces different hashes (salt)"""
        password = "test_password_123"
        hash1 = auth_adapter.get_password_hash(password)
        hash2 = auth_adapter.get_password_hash(password)
        
        # Hashes should be different due to salt
        assert hash1 != hash2
        # But both should verify correctly
        assert auth_adapter.verify_password(password, hash1) is True
        assert auth_adapter.verify_password(password, hash2) is True


class TestJWTTokens:
    """Tests for JWT token functionality"""

    def test_create_access_token(self, auth_adapter):
        """Test creating an access token"""
        data = {"sub": "testuser", "email": "test@example.com"}
        token = auth_adapter.create_access_token(data)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_valid_token(self, auth_adapter):
        """Test verifying a valid token"""
        data = {"sub": "testuser", "email": "test@example.com"}
        token = auth_adapter.create_access_token(data)
        
        payload = auth_adapter.verify_token(token)
        
        assert payload is not None
        assert payload["sub"] == "testuser"
        assert payload["email"] == "test@example.com"
        assert "exp" in payload

    def test_verify_invalid_token(self, auth_adapter):
        """Test verifying an invalid token"""
        invalid_token = "invalid.token.here"
        
        payload = auth_adapter.verify_token(invalid_token)
        
        assert payload is None

    def test_verify_token_with_wrong_secret(self, auth_adapter):
        """Test verifying token signed with different secret"""
        data = {"sub": "testuser"}
        # Create token with different secret
        wrong_token = jwt.encode(data, "wrong_secret", algorithm="HS256")
        
        payload = auth_adapter.verify_token(wrong_token)
        
        assert payload is None

    def test_create_token_with_custom_expiration(self, auth_adapter):
        """Test creating token with custom expiration"""
        data = {"sub": "testuser"}
        token = auth_adapter.create_access_token(data, expires_delta=60)
        
        payload = auth_adapter.verify_token(token)
        
        assert payload is not None
        assert payload["sub"] == "testuser"


class TestUserAuthentication:
    """Tests for user authentication"""

    def test_authenticate_valid_user(self, auth_adapter):
        """Test authenticating with valid credentials"""
        # Using the pre-configured admin user with password "admin123"
        user = auth_adapter.authenticate_user("admin", "admin123")
        
        assert user is not None
        assert user["username"] == "admin"
        assert user["email"] == "admin@jarvis.local"
        assert user["full_name"] == "Administrator"

    def test_authenticate_invalid_password(self, auth_adapter):
        """Test authenticating with invalid password"""
        user = auth_adapter.authenticate_user("admin", "wrong_password")
        
        assert user is None

    def test_authenticate_nonexistent_user(self, auth_adapter):
        """Test authenticating non-existent user"""
        user = auth_adapter.authenticate_user("nonexistent", "password")
        
        assert user is None

    def test_authenticate_returns_no_password(self, auth_adapter):
        """Test that authenticate doesn't return password hash"""
        user = auth_adapter.authenticate_user("admin", "admin123")
        
        assert user is not None
        assert "password" not in user
        assert "hashed_password" not in user
