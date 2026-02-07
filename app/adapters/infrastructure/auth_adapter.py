# -*- coding: utf-8 -*-
"""Authentication Adapter - Implementation of SecurityProvider using JWT and bcrypt"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, create_engine, select

from app.adapters.infrastructure.database_models import User
from app.application.ports.security_provider import SecurityProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthAdapter(SecurityProvider):
    """Authentication adapter implementing JWT and password hashing"""

    def __init__(self, database_url: Optional[str] = None):
        """Initialize the authentication adapter
        
        Args:
            database_url: Database connection URL. If None, uses settings.database_url
        """
        self.secret_key = settings.secret_key
        self.algorithm = settings.algorithm
        self.access_token_expire_minutes = settings.access_token_expire_minutes
        
        # Initialize database connection
        db_url = database_url or settings.database_url
        self.engine = create_engine(db_url, echo=False)

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
        try:
            with Session(self.engine) as session:
                # Query user from database
                statement = select(User).where(User.username == username)
                user = session.exec(statement).first()
                
                if not user:
                    logger.warning(f"Authentication failed: user '{username}' not found")
                    return None
                
                if not self.verify_password(password, user.hashed_password):
                    logger.warning(f"Authentication failed: invalid password for user '{username}'")
                    return None
                
                if user.disabled:
                    logger.warning(f"Authentication failed: user '{username}' is disabled")
                    return None
                
                return {
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                }
        except Exception as e:
            logger.error(f"Error authenticating user '{username}': {e}")
            return None
    
    def create_user(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        disabled: bool = False
    ) -> Optional[User]:
        """
        Create a new user in the database
        
        Args:
            username: The username
            password: The plain text password (will be hashed)
            email: Optional email address
            full_name: Optional full name
            disabled: Whether the user is disabled
            
        Returns:
            Created User object if successful, None otherwise
        """
        try:
            with Session(self.engine) as session:
                # Check if user already exists
                statement = select(User).where(User.username == username)
                existing_user = session.exec(statement).first()
                
                if existing_user:
                    logger.warning(f"User '{username}' already exists")
                    return None
                
                # Create new user
                hashed_password = self.get_password_hash(password)
                new_user = User(
                    username=username,
                    email=email,
                    full_name=full_name,
                    hashed_password=hashed_password,
                    disabled=disabled
                )
                
                session.add(new_user)
                session.commit()
                session.refresh(new_user)
                
                logger.info(f"Successfully created user '{username}'")
                return new_user
        except Exception as e:
            logger.error(f"Error creating user '{username}': {e}")
            return None
    
    def ensure_default_admin(self) -> None:
        """
        Ensure that a default admin user exists in the database.
        If no users exist, creates an admin user with username 'admin' and password 'admin123'
        """
        try:
            with Session(self.engine) as session:
                # Check if any users exist
                statement = select(User)
                users = session.exec(statement).all()
                
                if not users:
                    logger.info("No users found in database. Creating default admin user...")
                    
                    # Create default admin user
                    hashed_password = self.get_password_hash("admin123")
                    admin_user = User(
                        username="admin",
                        email="admin@jarvis.local",
                        full_name="Administrator",
                        hashed_password=hashed_password,
                        disabled=False
                    )
                    
                    session.add(admin_user)
                    session.commit()
                    
                    logger.info("✓ Default admin user created successfully (username: admin, password: admin123)")
                else:
                    logger.info(f"Database already has {len(users)} user(s)")
        except Exception as e:
            logger.error(f"Error ensuring default admin user: {e}")

