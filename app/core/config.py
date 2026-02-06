# -*- coding: utf-8 -*-
"""Configuration management for Jarvis Assistant using pydantic-settings"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and configuration"""

    # Application Settings
    app_name: str = "Jarvis Assistant"
    version: str = "1.0.0"

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

    # Security Settings
    secret_key: str = "your-secret-key-change-this-in-production-minimum-32-characters"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories if they don't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
