from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Authentication Adapter - Implementation of SecurityProvider using JWT and bcrypt.

Users are persisted in the ``users`` Supabase table (migration 003).  When
Supabase is not configured the adapter falls back to a single admin account
whose credentials are controlled by environment variables
``JARVIS_ADMIN_EMAIL`` / ``JARVIS_ADMIN_PASSWORD`` so that FAKE_USERS_DB is
never hardcoded in source.
"""

# IMPORTANT: Bcrypt compatibility hack MUST be at the top before any other imports
# Fix for: AttributeError: module 'bcrypt' has no attribute '__about__'
import bcrypt
if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type("About", (), {"__version__": bcrypt.__version__})

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.application.ports.security_provider import SecurityProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthAdapter(SecurityProvider):
    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    """Authentication adapter implementing JWT and password hashing.

    User lookup order:
    1. Supabase ``users`` table (if configured) — production path.
    2. Environment-variable-based admin fallback — development / no-cloud path.
    """

    def __init__(self):
        """Initialize the authentication adapter"""
        self.secret_key = settings.secret_key
        self.algorithm = settings.algorithm
        self.access_token_expire_minutes = settings.access_token_expire_minutes

    # ------------------------------------------------------------------
    # Supabase user helpers
    # ------------------------------------------------------------------

    def get_user_by_email(self, email: str) -> Optional[dict]:
        """Fetch a user record from the Supabase ``users`` table by e-mail.

        Args:
            email: The user's e-mail address.

        Returns:
            User dict or ``None`` if not found / Supabase unavailable.
        """
        try:
            from app.adapters.infrastructure.supabase_client import get_supabase_client

            client = get_supabase_client()
            if client is None:
                return None
            response = client.table("users").select("*").eq("email", email).limit(1).execute()
            rows = response.data
            if rows:
                return rows[0]
        except Exception as exc:
            logger.error("[AuthAdapter] Erro ao buscar usuário no Supabase: %s", exc)
        return None

    def get_user_by_username(self, username: str) -> Optional[dict]:
        """Fetch a user by email (username == email) from Supabase or fallback."""
        return self.get_user_by_email(username)

    def create_user(
        self,
        email: str,
        password: str,
        full_name: Optional[str] = None,
    ) -> Optional[dict]:
        """Create a new user in the Supabase ``users`` table.

        Args:
            email: User's e-mail address.
            password: Plain-text password (will be hashed before storage).
            full_name: Optional display name.

        Returns:
            Created user dict or ``None`` on failure.
        """
        try:
            from app.adapters.infrastructure.supabase_client import get_supabase_client

            client = get_supabase_client()
            if client is None:
                logger.warning("[AuthAdapter] Supabase indisponível; não é possível criar usuário.")
                return None
            hashed = self.get_password_hash(password)
            payload = {
                "email": email,
                "hashed_password": hashed,
                "full_name": full_name or "",
                "disabled": False,
            }
            response = client.table("users").insert(payload).execute()
            rows = response.data
            if rows:
                logger.info("[AuthAdapter] Usuário criado: %s", email)
                return rows[0]
        except Exception as exc:
            logger.error("[AuthAdapter] Erro ao criar usuário no Supabase: %s", exc)
        return None

    # ------------------------------------------------------------------
    # SecurityProvider interface
    # ------------------------------------------------------------------

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
        Authenticate a user with username (email) and password.

        Lookup order:
        1. Supabase ``users`` table when configured.
        2. Environment-variable admin fallback (``JARVIS_ADMIN_EMAIL`` /
           ``JARVIS_ADMIN_PASSWORD``) for local development.

        Args:
            username: The username / e-mail address.
            password: The plain text password.

        Returns:
            User data dict if authentication succeeds, None otherwise.
        """
        # --- 1. Supabase lookup ---
        user = self.get_user_by_email(username)
        if user is not None:
            if user.get("disabled", False):
                logger.warning("Authentication failed: user '%s' is disabled", username)
                return None
            stored_hash = user.get("hashed_password", "")
            if not stored_hash or not self.verify_password(password, stored_hash):
                logger.warning("Authentication failed: invalid password for user '%s'", username)
                return None
            return {
                "username": user.get("email", username),
                "email": user.get("email"),
                "full_name": user.get("full_name"),
                "user_id": str(user.get("id", "")),
            }

        # --- 2. Env-var admin fallback (no hardcoded credentials) ---
        admin_email = os.getenv("JARVIS_ADMIN_EMAIL", "admin@jarvis.local")
        admin_password = os.getenv("JARVIS_ADMIN_PASSWORD", "")
        if admin_password and username in (admin_email, "admin"):
            if password == admin_password:
                logger.info("Authentication via env-var admin fallback for '%s'", username)
                return {
                    "username": "admin",
                    "email": admin_email,
                    "full_name": "Administrator",
                    "user_id": "",
                }

        logger.warning("Authentication failed: user '%s' not found", username)
        return None
