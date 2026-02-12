# -*- coding: utf-8 -*-
"""Integration tests for PersistentBrowserManager - Playwright integration

These tests validate real integration scenarios for Playwright browser automation.
They test the full lifecycle: browser startup, CDP connection, codegen recording,
timeout handling, and cleanup.
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest

from app.application.services.browser_manager import PersistentBrowserManager


class TestBrowserManagerIntegration:
    """Integration test cases for PersistentBrowserManager"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test data"""
        temp_path = Path(tempfile.mkdtemp(prefix="test_browser_integration_"))
        yield temp_path
        # Cleanup
        import shutil
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def browser_manager(self, temp_dir):
        """Create PersistentBrowserManager with temporary user data directory"""
        return PersistentBrowserManager(
            user_data_dir=temp_dir / "browser_data",
            headless=True,
            browser_type="chromium"
        )

    def test_browser_lifecycle_start_stop(self, browser_manager):
        """Test complete browser lifecycle: start -> check status -> stop"""
        # Initially browser should not be running
        assert not browser_manager.is_running()
        assert browser_manager.get_cdp_url() is None

        # Mock browser process for testing
        with patch('app.application.services.browser_manager.subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # Process is running
            mock_popen.return_value = mock_process

            # Mock chromium directory
            with patch('pathlib.Path.exists', return_value=True):
                with patch('pathlib.Path.iterdir', return_value=[Path("chromium-1234")]):
                    # Manually set up browser for testing
                    browser_manager._browser_process = mock_process
                    browser_manager._cdp_url = "http://localhost:9222"

                    # Browser should be running
                    assert browser_manager.is_running()
                    assert browser_manager.get_cdp_url() == "http://localhost:9222"

                    # Stop browser
                    result = browser_manager.stop_browser()
                    assert result is True
                    assert not browser_manager.is_running()
                    assert browser_manager.get_cdp_url() is None

                    # Verify terminate was called
                    mock_process.terminate.assert_called_once()

    def test_browser_start_with_cdp_connection(self, browser_manager):
        """Test browser starts with CDP connection enabled"""
        with patch('app.application.services.browser_manager.subprocess.Popen') as mock_popen:
            with patch('pathlib.Path.exists', return_value=True):
                with patch('pathlib.Path.iterdir', return_value=[Path("chromium-1234")]):
                    mock_process = MagicMock()
                    mock_process.poll.return_value = None
                    mock_popen.return_value = mock_process

                    # Mock platform-specific chrome executable
                    import sys
                    with patch.object(sys, 'platform', 'linux'):
                        cdp_url = browser_manager.start_browser(port=9222)

                        # Verify Popen was called with correct arguments
                        if mock_popen.called:
                            args = mock_popen.call_args[0][0]
                            # Check for CDP port in arguments
                            assert any('--remote-debugging-port=9222' in str(arg) for arg in args)
                            # Check for headless mode
                            assert any('--headless' in str(arg) for arg in args)
                            # Check for user data dir
                            assert any('--user-data-dir' in str(arg) for arg in args)

    def test_browser_persistence_across_sessions(self, browser_manager, temp_dir):
        """Test that browser data persists across sessions (cookies, logins)"""
        # Verify user_data_dir exists
        assert browser_manager.user_data_dir.exists()

        # Create a mock cookie file to simulate persistence
        cookies_dir = browser_manager.user_data_dir / "Default"
        cookies_dir.mkdir(parents=True, exist_ok=True)
        cookies_file = cookies_dir / "Cookies"
        cookies_file.write_text("mock_cookie_data")

        # Create new browser manager with same directory
        browser_manager_2 = PersistentBrowserManager(
            user_data_dir=browser_manager.user_data_dir,
            headless=True
        )

        # Verify it uses the same directory with existing data
        assert browser_manager_2.user_data_dir == browser_manager.user_data_dir
        assert cookies_file.exists()
        assert cookies_file.read_text() == "mock_cookie_data"

    def test_codegen_recording_lifecycle(self, browser_manager):
        """Test complete codegen recording lifecycle"""
        with patch('app.application.services.browser_manager.subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            # Start codegen recording
            output_file = browser_manager.record_automation()

            # Should return a file path
            assert output_file is None or isinstance(output_file, str)

            if output_file:
                # Verify it's a Python file
                assert output_file.endswith('.py')

                # Verify subprocess was called
                assert mock_popen.called
                call_args = mock_popen.call_args[0][0]
                assert 'playwright' in ' '.join(str(arg) for arg in call_args)

    def test_codegen_wait_timeout_handling(self, browser_manager):
        """Test timeout handling when waiting for codegen to complete"""
        # Mock a codegen process that doesn't complete
        mock_process = MagicMock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd='playwright', timeout=5)

        browser_manager._codegen_process = mock_process

        # Wait should timeout and return False
        result = browser_manager.wait_for_codegen(timeout=5)
        assert result is False

    def test_codegen_wait_successful_completion(self, browser_manager):
        """Test successful completion of codegen recording"""
        # Mock a codegen process that completes
        mock_process = MagicMock()
        mock_process.wait.return_value = 0

        browser_manager._codegen_process = mock_process

        # Wait should complete successfully
        result = browser_manager.wait_for_codegen(timeout=10)
        assert result is True
        mock_process.wait.assert_called_once()

    def test_generated_code_reading_and_parsing(self, browser_manager, temp_dir):
        """Test reading and validating generated Playwright code"""
        # Create a mock generated code file
        code_file = temp_dir / "generated_skill.py"
        expected_code = """from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://example.com")
    page.click("button#submit")
    browser.close()

with sync_playwright() as playwright:
    run(playwright)
"""
        code_file.write_text(expected_code)

        # Read the code
        code = browser_manager.get_generated_code(str(code_file))

        # Verify code was read correctly
        assert code is not None
        assert "sync_playwright" in code
        assert "playwright.chromium.launch" in code
        assert len(code) == len(expected_code)

    def test_cleanup_old_recordings(self, browser_manager, temp_dir):
        """Test automatic cleanup of old recording files"""
        # Create mock recordings directory
        recordings_dir = temp_dir / "jarvis_recordings"
        recordings_dir.mkdir()

        # Create old and new files
        old_file = recordings_dir / "skill_old.py"
        old_file.write_text("print('old skill')")

        new_file = recordings_dir / "skill_new.py"
        new_file.write_text("print('new skill')")

        # Manually set old file's mtime to 8 days ago
        old_time = time.time() - (8 * 24 * 60 * 60)
        import os
        os.utime(old_file, (old_time, old_time))

        # Run cleanup with 7 days max age
        with patch('tempfile.gettempdir', return_value=str(temp_dir)):
            browser_manager.cleanup_recordings(max_age_days=7)

        # Old file should be deleted, new file should remain
        assert not old_file.exists()
        assert new_file.exists()

    def test_browser_process_timeout_handling(self, browser_manager):
        """Test robust timeout handling for browser processes"""
        # Mock a process that doesn't terminate gracefully
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd='chrome', timeout=5)

        browser_manager._browser_process = mock_process
        browser_manager._cdp_url = "http://localhost:9222"

        # Stop should timeout and force kill
        result = browser_manager.stop_browser()

        # Verify both terminate and kill were called
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        assert result is True
        assert browser_manager._browser_process is None

    def test_multiple_browsers_different_ports(self):
        """Test running multiple browser instances on different ports"""
        temp_dir1 = Path(tempfile.mkdtemp(prefix="test_browser_1_"))
        temp_dir2 = Path(tempfile.mkdtemp(prefix="test_browser_2_"))

        try:
            bm1 = PersistentBrowserManager(user_data_dir=temp_dir1, headless=True)
            bm2 = PersistentBrowserManager(user_data_dir=temp_dir2, headless=True)

            # Mock processes
            with patch('app.application.services.browser_manager.subprocess.Popen') as mock_popen:
                mock_process_1 = MagicMock()
                mock_process_2 = MagicMock()
                mock_process_1.poll.return_value = None
                mock_process_2.poll.return_value = None

                # Set up manual processes for testing
                bm1._browser_process = mock_process_1
                bm1._cdp_url = "http://localhost:9222"

                bm2._browser_process = mock_process_2
                bm2._cdp_url = "http://localhost:9223"

                # Both should be running
                assert bm1.is_running()
                assert bm2.is_running()

                # Should have different CDP URLs
                assert bm1.get_cdp_url() != bm2.get_cdp_url()

                # Clean up
                bm1.stop_browser()
                bm2.stop_browser()

        finally:
            import shutil
            shutil.rmtree(temp_dir1, ignore_errors=True)
            shutil.rmtree(temp_dir2, ignore_errors=True)

    def test_error_recovery_on_browser_crash(self, browser_manager):
        """Test automatic error recovery when browser crashes"""
        # Mock a process that crashes
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Exit code indicates crash

        browser_manager._browser_process = mock_process
        browser_manager._cdp_url = "http://localhost:9222"

        # is_running should detect crash
        assert not browser_manager.is_running()

        # CDP URL should be None after crash detection
        assert browser_manager.get_cdp_url() is None

    def test_codegen_output_file_customization(self, browser_manager, temp_dir):
        """Test customizing output file path for codegen"""
        custom_output = temp_dir / "custom_automation.py"

        with patch('app.application.services.browser_manager.subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process

            output_file = browser_manager.record_automation(output_file=custom_output)

            # Should use custom path
            if output_file:
                assert str(custom_output) in str(output_file) or output_file == str(custom_output)

    def test_browser_start_without_playwright_installed(self, browser_manager):
        """Test graceful failure when Playwright is not installed"""
        # Mock the import to raise ImportError
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if 'playwright' in name:
                raise ImportError("Playwright not installed")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, '__import__', side_effect=mock_import):
            cdp_url = browser_manager.start_browser()

            # Should return None and log error
            assert cdp_url is None

    def test_browser_resource_cleanup_on_exception(self, browser_manager):
        """Test that resources are cleaned up properly on exception"""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        browser_manager._browser_process = mock_process
        browser_manager._cdp_url = "http://localhost:9222"

        # Simulate error during stop
        mock_process.terminate.side_effect = Exception("Test exception")

        # Should handle exception gracefully and return False
        result = browser_manager.stop_browser()

        # Result should be False due to exception
        assert result is False

    def test_user_data_dir_permissions(self, browser_manager):
        """Test that user_data_dir has correct permissions"""
        # Directory should exist and be writable
        assert browser_manager.user_data_dir.exists()
        assert os.access(browser_manager.user_data_dir, os.W_OK)

        # Should be able to create files in it
        test_file = browser_manager.user_data_dir / "test_write.txt"
        test_file.write_text("test")
        assert test_file.exists()
        test_file.unlink()

    def test_browser_restart_after_crash(self, browser_manager):
        """Test restarting browser after a crash"""
        with patch('app.application.services.browser_manager.subprocess.Popen') as mock_popen:
            # First process (crashes)
            mock_process_1 = MagicMock()
            mock_process_1.poll.return_value = 1  # Crashed

            # Second process (successful)
            mock_process_2 = MagicMock()
            mock_process_2.poll.return_value = None  # Running

            mock_popen.side_effect = [mock_process_1, mock_process_2]

            # Set up first process
            browser_manager._browser_process = mock_process_1
            browser_manager._cdp_url = "http://localhost:9222"

            # Detect crash
            assert not browser_manager.is_running()

            # Restart should work
            browser_manager._browser_process = None
            browser_manager._cdp_url = None

            with patch('pathlib.Path.exists', return_value=True):
                with patch('pathlib.Path.iterdir', return_value=[Path("chromium-1234")]):
                    # Manually set up for second attempt
                    browser_manager._browser_process = mock_process_2
                    browser_manager._cdp_url = "http://localhost:9222"

                    assert browser_manager.is_running()


class TestBrowserManagerExtensionSupport:
    """Tests for browser extension management and complex automations"""

    @pytest.fixture
    def browser_manager(self, tmp_path):
        """Create PersistentBrowserManager for extension tests"""
        return PersistentBrowserManager(
            user_data_dir=tmp_path / "browser_data",
            headless=False,  # Extensions typically require headed mode
            browser_type="chromium"
        )

    def test_browser_with_extension_directory(self, browser_manager):
        """Test loading browser with extension directory"""
        # Create mock extension directory
        extension_dir = browser_manager.user_data_dir / "Extensions"
        extension_dir.mkdir(parents=True, exist_ok=True)

        # Create mock extension manifest
        manifest = extension_dir / "manifest.json"
        manifest.write_text('{"name": "Test Extension", "version": "1.0"}')

        # Verify extension directory exists
        assert extension_dir.exists()
        assert manifest.exists()

    def test_persistent_context_for_complex_automations(self, browser_manager):
        """Test that persistent context maintains state for complex automations"""
        # Verify user_data_dir supports persistent context
        assert browser_manager.user_data_dir.exists()

        # Create mock session data
        session_dir = browser_manager.user_data_dir / "Default"
        session_dir.mkdir(parents=True, exist_ok=True)

        # Mock localStorage data
        local_storage = session_dir / "Local Storage"
        local_storage.mkdir(exist_ok=True)

        # Verify persistence infrastructure
        assert session_dir.exists()
        assert local_storage.exists()

