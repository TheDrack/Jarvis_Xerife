# -*- coding: utf-8 -*-
"""Authentication Adapter - Implementation of SecurityProvider using JWT and bcrypt"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.application.ports.security_provider import SecurityProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Mock user database - in production, this should be replaced with a real database
# Password: "admin123" (pre-hashed)
FAKE_USERS_DB = {
    "admin": {
        "username": "admin",
        "full_name": "Administrator",
        "email": "admin@jarvis.local",
        "hashed_password": "$2b$12$MYFM.Syb6/1Mz8abGMtLoOb3nNpMq3NCl1/bcXsToqcO.eT77ajt6",
        "disabled": False,
    }
}


class AuthAdapter(SecurityProvider):
    """Authentication adapter implementing JWT and password hashing"""

    def __init__(self):
        """Initialize the authentication adapter"""
        self.secret_key = settings.secret_key
        self.algorithm = settings.algorithm
        self.access_token_expire_minutes = settings.access_token_expire_minutes

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify a plain password against a hashed password

        Args:
            plain_password: The plain text password to verify
            hashed_password: The hashed password to compare against

        Returns:
            True if the password matches, False otherwise
        """
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.error(f"Error verifying password: {e}")
            return False

    def get_password_hash(self, password: str) -> str:
        """
        Hash a password using bcrypt

        Args:
            password: The plain text password to hash

        Returns:
            The hashed password
        """
        return pwd_context.hash(password)

    def create_access_token(self, data: dict, expires_delta: Optional[int] = None) -> str:
        """
        Create a JWT access token

        Args:
            data: The data to encode in the token
            expires_delta: Optional expiration time in minutes

        Returns:
            The encoded JWT token
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=expires_delta)
        else:
            expire = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[dict]:
        """
        Verify and decode a JWT token

        Args:
            token: The JWT token to verify

        Returns:
            The decoded token data if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            logger.error(f"Error verifying token: {e}")
            return None

    def authenticate_user(self, username: str, password: str) -> Optional[dict]:
        """
        Authenticate a user with username and password

        Args:
            username: The username
            password: The plain text password

        Returns:
            User data if authentication succeeds, None otherwise
        """
        user = FAKE_USERS_DB.get(username)
        if not user:
            logger.warning(f"Authentication failed: user '{username}' not found")
            return None
        
        if not self.verify_password(password, user["hashed_password"]):
            logger.warning(f"Authentication failed: invalid password for user '{username}'")
            return None
        
        if user.get("disabled", False):
            logger.warning(f"Authentication failed: user '{username}' is disabled")
            return None
        
        return {
            "username": user["username"],
            "email": user["email"],
            "full_name": user["full_name"],
        }
