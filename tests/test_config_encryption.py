# -*- coding: utf-8 -*-
"""Tests for configuration decryption functionality"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.encryption import encrypt_value


class TestConfigDecryption:
    """Test cases for configuration loading with encrypted values"""

    def test_config_loads_encrypted_api_key(self, tmp_path):
        """Test that Settings correctly decrypts GEMINI_API_KEY"""
        # Create a temporary .env file with encrypted API key
        api_key = "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"
        encrypted_api_key = encrypt_value(api_key)
        
        env_file = tmp_path / ".env"
        env_file.write_text(f"GEMINI_API_KEY={encrypted_api_key}\n")
        
        # Import Settings with the test .env file
        from pydantic_settings import SettingsConfigDict
        from app.core.config import Settings
        
        with patch.object(Settings, 'model_config', SettingsConfigDict(
            env_file=str(env_file),
            env_file_encoding="utf-8",
            case_sensitive=False,
        )):
            settings = Settings(_env_file=str(env_file))
            assert settings.gemini_api_key == api_key

    def test_config_loads_encrypted_database_url(self, tmp_path):
        """Test that Settings correctly decrypts DATABASE_URL"""
        # Create a temporary .env file with encrypted database URL
        database_url = "postgresql://user:pass@localhost:5432/db"
        encrypted_database_url = encrypt_value(database_url)
        
        env_file = tmp_path / ".env"
        env_file.write_text(f"DATABASE_URL={encrypted_database_url}\n")
        
        from app.core.config import Settings
        
        settings = Settings(_env_file=str(env_file))
        assert settings.database_url == database_url

    def test_config_loads_plain_text_values(self, tmp_path):
        """Test that Settings still works with plain text (unencrypted) values"""
        # Create a temporary .env file with plain text values
        api_key = "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"
        database_url = "sqlite:///jarvis.db"
        
        env_file = tmp_path / ".env"
        env_file.write_text(f"""
GEMINI_API_KEY={api_key}
DATABASE_URL={database_url}
""")
        
        from app.core.config import Settings
        
        settings = Settings(_env_file=str(env_file))
        assert settings.gemini_api_key == api_key
        assert settings.database_url == database_url

    def test_config_fails_with_wrong_hardware_encrypted_value(self, tmp_path):
        """Test that Settings raises error when encrypted value can't be decrypted"""
        # Create encrypted value with current hardware
        api_key = "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"
        encrypted_api_key = encrypt_value(api_key)
        
        env_file = tmp_path / ".env"
        env_file.write_text(f"GEMINI_API_KEY={encrypted_api_key}\n")
        
        # Mock a different hardware ID to simulate moving to different machine
        with patch('app.core.encryption.get_hardware_id') as mock_hardware_id:
            mock_hardware_id.return_value = "different-hardware-id-12345"
            
            from app.core.config import Settings
            
            with pytest.raises(ValueError, match="Failed to decrypt GEMINI_API_KEY"):
                Settings(_env_file=str(env_file))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
