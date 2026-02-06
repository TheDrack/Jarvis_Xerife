# -*- coding: utf-8 -*-
"""Security Provider Interface - Port for authentication and authorization"""

from abc import ABC, abstractmethod
from typing import Optional


class SecurityProvider(ABC):
    """Interface for security and authentication operations"""

    @abstractmethod
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify a plain password against a hashed password

        Args:
            plain_password: The plain text password to verify
            hashed_password: The hashed password to compare against

        Returns:
            True if the password matches, False otherwise
        """
        pass

    @abstractmethod
    def get_password_hash(self, password: str) -> str:
        """
        Hash a password using bcrypt

        Args:
            password: The plain text password to hash

        Returns:
            The hashed password
        """
        pass

    @abstractmethod
    def create_access_token(self, data: dict, expires_delta: Optional[int] = None) -> str:
        """
        Create a JWT access token

        Args:
            data: The data to encode in the token
            expires_delta: Optional expiration time in minutes

        Returns:
            The encoded JWT token
        """
        pass

    @abstractmethod
    def verify_token(self, token: str) -> Optional[dict]:
        """
        Verify and decode a JWT token

        Args:
            token: The JWT token to verify

        Returns:
            The decoded token data if valid, None otherwise
        """
        pass

    @abstractmethod
    def authenticate_user(self, username: str, password: str) -> Optional[dict]:
        """
        Authenticate a user with username and password

        Args:
            username: The username
            password: The plain text password

        Returns:
            User data if authentication succeeds, None otherwise
        """
        pass
