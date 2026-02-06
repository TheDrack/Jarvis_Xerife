# -*- coding: utf-8 -*-
"""Tests for Setup Wizard functionality"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.fixture(scope="module", autouse=True)
def mock_pyperclip():
    """Mock pyperclip module before importing setup_wizard to avoid import errors"""
    # Store original module if it existed
    original_pyperclip = sys.modules.get('pyperclip')
    
    # Install mock
    mock_module = Mock()
    sys.modules['pyperclip'] = mock_module
    yield mock_module
    
    # Cleanup - restore original module or remove mock
    if original_pyperclip is not None:
        sys.modules['pyperclip'] = original_pyperclip
    elif 'pyperclip' in sys.modules:
        del sys.modules['pyperclip']


from app.adapters.infrastructure.setup_wizard import (
    check_env_complete,
    save_env_file,
    validate_database_connection,
)


class TestSetupWizard:
    """Test cases for setup wizard functions"""
    
    def test_check_env_complete_missing_file(self, tmp_path):
        """Test that check_env_complete returns False when .env doesn't exist"""
        with patch('app.adapters.infrastructure.setup_wizard.Path') as mock_path:
            mock_base_dir = MagicMock()
            mock_base_dir.__truediv__ = MagicMock(return_value=tmp_path / "nonexistent.env")
            mock_path.return_value.parent.parent.parent.parent = mock_base_dir
            
            # The file doesn't exist
            result = check_env_complete()
            assert result is False
    
    def test_check_env_complete_with_all_fields(self, tmp_path):
        """Test that check_env_complete returns True when all required fields exist"""
        env_file = tmp_path / ".env"
        env_file.write_text("""
GEMINI_API_KEY=test_key_123
USER_ID=user_123
ASSISTANT_NAME=TestBot
DATABASE_URL=sqlite:///test.db
""")
        
        with patch('app.adapters.infrastructure.setup_wizard.Path') as mock_path:
            mock_base_dir = MagicMock()
            mock_base_dir.__truediv__ = MagicMock(return_value=env_file)
            mock_path.return_value.parent.parent.parent.parent = mock_base_dir
            
            result = check_env_complete()
            assert result is True
    
    def test_check_env_complete_with_missing_fields(self, tmp_path):
        """Test that check_env_complete returns False when required fields are missing"""
        env_file = tmp_path / ".env"
        env_file.write_text("""
GEMINI_API_KEY=test_key_123
DATABASE_URL=sqlite:///test.db
""")
        
        with patch('app.adapters.infrastructure.setup_wizard.Path') as mock_path:
            mock_base_dir = MagicMock()
            mock_base_dir.__truediv__ = MagicMock(return_value=env_file)
            mock_path.return_value.parent.parent.parent.parent = mock_base_dir
            
            result = check_env_complete()
            assert result is False
    
    def test_check_env_complete_with_empty_values(self, tmp_path):
        """Test that check_env_complete returns False when fields have empty values"""
        env_file = tmp_path / ".env"
        env_file.write_text("""
GEMINI_API_KEY=
USER_ID=user_123
ASSISTANT_NAME=TestBot
""")
        
        with patch('app.adapters.infrastructure.setup_wizard.Path') as mock_path:
            mock_base_dir = MagicMock()
            mock_base_dir.__truediv__ = MagicMock(return_value=env_file)
            mock_path.return_value.parent.parent.parent.parent = mock_base_dir
            
            result = check_env_complete()
            assert result is False
    
    def test_save_env_file_creates_file(self, tmp_path):
        """Test that save_env_file creates a valid .env file"""
        assistant_name = "Jarvis"
        user_id = "user_123"
        api_key = "test_api_key_AIzaSy123"
        database_url = "sqlite:///jarvis.db"
        
        # Create .env.example with USER_ID and ASSISTANT_NAME placeholders
        env_example = tmp_path / ".env.example"
        env_example.write_text("""# Example config
APP_NAME=Jarvis Assistant
USER_ID=
ASSISTANT_NAME=
GEMINI_API_KEY=your_key_here
DATABASE_URL=sqlite:///jarvis.db
""")
        
        result = save_env_file(assistant_name, user_id, api_key, database_url, tmp_path)
        
        assert result is True
        
        env_file = tmp_path / ".env"
        assert env_file.exists()
        
        content = env_file.read_text()
        assert f"USER_ID={user_id}" in content
        assert f"ASSISTANT_NAME={assistant_name}" in content
        assert f"GEMINI_API_KEY={api_key}" in content
        assert f"DATABASE_URL={database_url}" in content
    
    def test_save_env_file_without_example(self, tmp_path):
        """Test that save_env_file works even without .env.example"""
        assistant_name = "Jarvis"
        user_id = "user_123"
        api_key = "test_api_key_AIzaSy123"
        database_url = "postgresql://user:pass@host:5432/db"
        
        result = save_env_file(assistant_name, user_id, api_key, database_url, tmp_path)
        
        assert result is True
        
        env_file = tmp_path / ".env"
        assert env_file.exists()
        
        content = env_file.read_text()
        assert f"USER_ID={user_id}" in content
        assert f"ASSISTANT_NAME={assistant_name}" in content
        assert f"GEMINI_API_KEY={api_key}" in content
        assert f"DATABASE_URL={database_url}" in content
    
    def test_validate_database_connection_sqlite(self):
        """Test database validation with SQLite (should always work)"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
            db_path = tmp_db.name
        
        try:
            database_url = f"sqlite:///{db_path}"
            result = validate_database_connection(database_url)
            assert result is True
        finally:
            # Clean up
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_validate_database_connection_invalid_url(self):
        """Test database validation with invalid URL"""
        database_url = "invalid://connection/string"
        result = validate_database_connection(database_url)
        assert result is False
    
    @patch('app.adapters.infrastructure.setup_wizard.webbrowser.open')
    @patch('app.adapters.infrastructure.setup_wizard.input')
    def test_get_api_key_with_clipboard_auto_capture(self, mock_input, mock_browser):
        """Test API key capture with automatic clipboard detection"""
        # Import and patch pyperclip at module level
        import app.adapters.infrastructure.setup_wizard as wizard_module
        
        with patch.object(wizard_module, 'pyperclip') as mock_pyperclip:
            with patch.object(wizard_module, 'CLIPBOARD_AVAILABLE', True):
                # Simulate clipboard behavior:
                # First call (initial state): empty clipboard before user copies API key
                # Second call (after user copies): API key is now in clipboard
                mock_pyperclip.paste.side_effect = ["", "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"]
                mock_input.side_effect = ["", "s"]  # Press enter to open browser, then confirm
                
                result = wizard_module.get_api_key_with_clipboard()
                
                assert result == "AIzaSyB38zXj77_eNGKb2nB5NfrQKl1s7XwIpIc"
                assert mock_browser.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
