# -*- coding: utf-8 -*-
"""Configuration management for Jarvis Assistant using pydantic-settings"""

import logging
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.encryption import decrypt_value, is_encrypted

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings and configuration"""

    # Application Settings
    app_name: str = "Jarvis Assistant"
    version: str = "1.0.0"

    # User Settings
    user_id: Optional[str] = None
    assistant_name: Optional[str] = None

    # Voice Recognition Settings
    language: str = "pt-BR"
    wake_word: str = "xerife"

    # Paths
    base_dir: Path = Path(__file__).parent.parent.parent
    data_dir: Path = base_dir / "data"
    logs_dir: Path = base_dir / "logs"

    # Audio Settings
    ambient_noise_adjustment: bool = True
    recognition_timeout: Optional[float] = None

    # PyAutoGUI Settings
    pyautogui_pause: float = 0.4
    search_timeout: float = 7.5

    # LLM Settings
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-1.5-flash"

    # Security Settings
    secret_key: str = "your-secret-key-change-this-in-production-minimum-32-characters"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Database Settings
    database_url: str = "sqlite:///jarvis.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra='allow',
        # System environment variables automatically override .env file values
        # This is the default behavior in pydantic-settings (env vars have higher priority)
    )

    @field_validator('gemini_api_key', mode='before')
    @classmethod
    def decrypt_api_key(cls, v: Optional[str]) -> Optional[str]:
        """Decrypt GEMINI_API_KEY if it's encrypted"""
        if v and is_encrypted(v):
            try:
                decrypted = decrypt_value(v)
                logger.info("Successfully decrypted GEMINI_API_KEY")
                return decrypted
            except Exception as e:
                logger.error(f"Failed to decrypt GEMINI_API_KEY: {type(e).__name__}")
                logger.error("The .env file may have been moved to a different machine.")
                logger.error("Please run the setup wizard again to reconfigure.")
                raise ValueError(
                    "Failed to decrypt GEMINI_API_KEY. "
                    "The .env file may have been moved to a different machine. "
                    "Please run the setup wizard again."
                ) from e
        return v

    @field_validator('database_url', mode='before')
    @classmethod
    def decrypt_database_url(cls, v: str) -> str:
        """Decrypt DATABASE_URL if it's encrypted"""
        if v and is_encrypted(v):
            try:
                decrypted = decrypt_value(v)
                logger.info("Successfully decrypted DATABASE_URL")
                return decrypted
            except Exception as e:
                logger.error(f"Failed to decrypt DATABASE_URL: {type(e).__name__}")
                logger.error("The .env file may have been moved to a different machine.")
                logger.error("Please run the setup wizard again to reconfigure.")
                raise ValueError(
                    "Failed to decrypt DATABASE_URL. "
                    "The .env file may have been moved to a different machine. "
                    "Please run the setup wizard again."
                ) from e
        return v

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories if they don't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
