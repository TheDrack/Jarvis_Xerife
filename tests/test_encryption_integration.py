# -*- coding: utf-8 -*-
"""Integration test for the complete encryption flow"""

import tempfile
from pathlib import Path

import pytest

from app.adapters.infrastructure.setup_wizard import save_env_file
from app.core.config import Settings
from app.core.encryption import decrypt_value, is_encrypted


class TestEncryptionIntegration:
    """Integration tests for the complete encryption workflow"""

    def test_complete_flow_setup_to_load(self, tmp_path):
        """
        Test the complete flow:
        1. Setup wizard saves encrypted .env
        2. Settings loads and decrypts values
        """
        # Step 1: Setup wizard saves encrypted values
        assistant_name = "Jarvis"
        user_id = "user_123"
        api_key = "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"
        database_url = "postgresql://postgres:password@db.example.com:5432/postgres"
        
        # Create .env.example
        env_example = tmp_path / ".env.example"
        env_example.write_text("""# Example config
APP_NAME=Jarvis Assistant
USER_ID=
ASSISTANT_NAME=
GEMINI_API_KEY=your_key_here
DATABASE_URL=sqlite:///jarvis.db
""")
        
        # Save env file (should encrypt sensitive values)
        result = save_env_file(assistant_name, user_id, api_key, database_url, tmp_path)
        assert result is True
        
        # Step 2: Verify file was created with encrypted values
        env_file = tmp_path / ".env"
        assert env_file.exists()
        
        content = env_file.read_text()
        
        # Verify user settings are NOT encrypted
        assert f"USER_ID={user_id}" in content
        assert f"ASSISTANT_NAME={assistant_name}" in content
        
        # Verify sensitive values ARE encrypted
        assert api_key not in content  # Plain text should not be in file
        assert database_url not in content  # Plain text should not be in file
        assert "GEMINI_API_KEY=ENCRYPTED:" in content
        assert "DATABASE_URL=ENCRYPTED:" in content
        
        # Step 3: Load settings and verify decryption works
        settings = Settings(_env_file=str(env_file))
        
        assert settings.user_id == user_id
        assert settings.assistant_name == assistant_name
        assert settings.gemini_api_key == api_key  # Should be decrypted
        assert settings.database_url == database_url  # Should be decrypted
        
    def test_encrypted_env_cannot_be_moved_to_different_hardware(self, tmp_path):
        """
        Test that .env file encrypted on one machine cannot be used on another
        """
        from unittest.mock import patch
        
        # Step 1: Create encrypted .env on "machine 1"
        api_key = "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"
        database_url = "postgresql://postgres:password@db.example.com:5432/postgres"
        
        env_example = tmp_path / ".env.example"
        env_example.write_text("""
GEMINI_API_KEY=your_key_here
DATABASE_URL=sqlite:///jarvis.db
""")
        
        result = save_env_file("Jarvis", "user_123", api_key, database_url, tmp_path)
        assert result is True
        
        env_file = tmp_path / ".env"
        
        # Step 2: Try to load on "machine 2" (different hardware ID)
        with patch('app.core.encryption.get_hardware_id') as mock_hardware_id:
            mock_hardware_id.return_value = "different-hardware-id-12345"
            
            # Loading settings should fail
            with pytest.raises(ValueError, match="Failed to decrypt"):
                Settings(_env_file=str(env_file))
    
    def test_manual_verification_of_encrypted_values(self, tmp_path):
        """
        Test that we can manually decrypt values from .env if needed
        """
        # Save encrypted .env
        api_key = "test_secret_key_123"
        database_url = "postgresql://user:pass@host:5432/db"
        
        result = save_env_file("Bot", "user_456", api_key, database_url, tmp_path)
        assert result is True
        
        # Read the encrypted values directly from file
        env_file = tmp_path / ".env"
        content = env_file.read_text()
        
        # Extract encrypted API key
        for line in content.split('\n'):
            if line.startswith('GEMINI_API_KEY='):
                encrypted_api_key = line.split('=', 1)[1]
                assert is_encrypted(encrypted_api_key)
                
                # Manually decrypt
                decrypted = decrypt_value(encrypted_api_key)
                assert decrypted == api_key
                
            elif line.startswith('DATABASE_URL='):
                encrypted_db_url = line.split('=', 1)[1]
                assert is_encrypted(encrypted_db_url)
                
                # Manually decrypt
                decrypted = decrypt_value(encrypted_db_url)
                assert decrypted == database_url


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
