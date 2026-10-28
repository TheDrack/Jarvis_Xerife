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

from app.application.ports.security_provider import SecurityProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

# bcrypt limita o segredo a 72 bytes. Truncamos explicitamente em vez de
# depender do backend: bcrypt >= 4.1 levanta ValueError em vez de truncar, e
# passlib 1.7.4 (usado antes) falha na detecção de backend com esse bcrypt,
# quebrando TODA a verificação de senha.
_BCRYPT_MAX_BYTES = 72


def _prepare_secret(password: str) -> bytes:
    """Converte a senha em bytes seguros para o bcrypt (máx. 72 bytes)."""
    raw = password.encode("utf-8")
    return raw[:_BCRYPT_MAX_BYTES]


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
        """Look up a custom Jarvis user using the server-only client when available.

        Existing deployments contain the legacy singular public.user table;
        newer code also encountered public.users. Support both schemas while
        keeping password hashes behind the server's service-role client.
        """
        try:
            from app.adapters.infrastructure.supabase_client import get_supabase_admin_client

            # Password hashes must only be read with server-side privileges.
            # Never fall back to the public/publishable Supabase client.
            client = get_supabase_admin_client()
            if client is None:
                return None

            for table_name in ("user", "users"):
                for column_name in ("email", "username"):
                    try:
                        response = (
                            client.table(table_name)
                            .select("*")
                            .eq(column_name, email)
                            .limit(1)
                            .execute()
                        )
                        rows = response.data or []
                        if rows:
                            return rows[0]
                    except Exception as exc:
                        # Historical schemas may not contain a table/column.
                        # Do not log account identifiers or credential data.
                        logger.debug(
                            "[AuthAdapter] User lookup skipped for %s.%s (%s)",
                            table_name,
                            column_name,
                            type(exc).__name__,
                        )
        except Exception as exc:
            logger.error("[AuthAdapter] User lookup failed (%s)", type(exc).__name__)
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
        """Create a user using server-only database privileges."""
        try:
            from app.adapters.infrastructure.supabase_client import get_supabase_admin_client

            client = get_supabase_admin_client()
            if client is None:
                logger.warning(
                    "[AuthAdapter] Admin database client unavailable; user creation refused."
                )
                return None
            normalized_email = email.strip().lower()
            if not normalized_email or not password:
                return None
            payload = {
                "username": normalized_email,
                "email": normalized_email,
                "hashed_password": self.get_password_hash(password),
                "full_name": full_name or "",
                "disabled": False,
            }
            response = client.table("user").insert(payload).execute()
            rows = response.data or []
            if rows:
                logger.info("[AuthAdapter] User created successfully.")
                return rows[0]
        except Exception as exc:
            logger.error("[AuthAdapter] User creation failed (%s)", type(exc).__name__)
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
            return bcrypt.checkpw(
                _prepare_secret(plain_password), hashed_password.encode("utf-8")
            )
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
        return bcrypt.hashpw(_prepare_secret(password), bcrypt.gensalt()).decode("utf-8")

    def _require_signing_key(self) -> None:
        """Fail closed unless a deployment-specific JWT secret is configured."""
        key = self.secret_key
        if (
            not isinstance(key, str)
            or len(key) < 32
            or key.startswith("your-secret-key")
            or key.lower() in {"changeme", "change-me", "secret", "development"}
        ):
            raise RuntimeError(
                "SECRET_KEY is missing or insecure; configure a random secret of at least 32 characters."
            )

    def create_access_token(self, data: dict, expires_delta: Optional[int] = None) -> str:
        """
        Create a JWT access token

        Args:
            data: The data to encode in the token
            expires_delta: Optional expiration time in minutes

        Returns:
            The encoded JWT token
        """
        self._require_signing_key()
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
            self._require_signing_key()
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
            canonical_username = user.get("email") or user.get("username") or username
            return {
                "username": canonical_username,
                "email": user.get("email") or user.get("username"),
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
