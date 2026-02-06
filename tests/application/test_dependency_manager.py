# -*- coding: utf-8 -*-
"""Tests for DependencyManager Service"""

import sys
from unittest.mock import Mock, patch

import pytest

from app.application.services import DependencyManager


class TestDependencyManager:
    """Test cases for DependencyManager"""

    @pytest.fixture
    def manager(self):
        """Create a DependencyManager instance"""
        return DependencyManager()

    def test_initialization(self, manager):
        """Test that manager initializes correctly"""
        assert manager is not None
        assert isinstance(manager._installed_capabilities, set)
        assert len(manager._installed_capabilities) == 0

    def test_check_module_installed_success(self, manager):
        """Test checking for an installed module"""
        # sys is always available
        assert manager._check_module_installed("sys") is True

    def test_check_module_installed_failure(self, manager):
        """Test checking for a non-existent module"""
        assert manager._check_module_installed("nonexistent_module_xyz") is False

    def test_is_capability_available_for_installed(self, manager):
        """Test checking availability of an installed module"""
        # sys is always available
        assert manager.is_capability_available("sys") is True

    def test_is_capability_available_for_missing(self, manager):
        """Test checking availability of a missing module"""
        assert manager.is_capability_available("nonexistent_module_xyz") is False

    def test_get_installed_capabilities_empty(self, manager):
        """Test getting capabilities when none are confirmed"""
        capabilities = manager.get_installed_capabilities()
        assert isinstance(capabilities, set)
        assert len(capabilities) == 0

    def test_get_installed_capabilities_after_ensure(self, manager):
        """Test that confirmed capabilities are tracked"""
        # Mock the methods to simulate successful installation
        with patch.object(manager, '_check_module_installed', return_value=True):
            manager.ensure_capability("pandas")
            capabilities = manager.get_installed_capabilities()
            assert "pandas" in capabilities

    @patch('subprocess.run')
    def test_install_package_success(self, mock_run, manager):
        """Test successful package installation"""
        # Mock successful installation
        mock_run.return_value = Mock(returncode=0, stdout="Successfully installed", stderr="")
        
        result = manager._install_package("test-package")
        
        assert result is True
        mock_run.assert_called_once()
        # Check that pip install was called with correct arguments
        call_args = mock_run.call_args[0][0]
        assert sys.executable in call_args
        assert "-m" in call_args
        assert "pip" in call_args
        assert "install" in call_args
        assert "test-package" in call_args

    @patch('subprocess.run')
    def test_install_package_failure(self, mock_run, manager):
        """Test failed package installation"""
        # Mock failed installation
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error installing")
        
        result = manager._install_package("test-package")
        
        assert result is False

    @patch('subprocess.run')
    def test_install_package_timeout(self, mock_run, manager):
        """Test package installation timeout"""
        import subprocess
        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired("pip", 300)
        
        result = manager._install_package("test-package")
        
        assert result is False

    @patch('subprocess.run')
    def test_install_package_exception(self, mock_run, manager):
        """Test package installation with exception"""
        # Mock exception
        mock_run.side_effect = Exception("Unexpected error")
        
        result = manager._install_package("test-package")
        
        assert result is False

    def test_ensure_capability_already_installed(self, manager):
        """Test ensure_capability when module is already available"""
        # sys is always available
        result = manager.ensure_capability("sys")
        
        assert result is True
        assert "sys" in manager._installed_capabilities

    def test_ensure_capability_cached(self, manager):
        """Test that ensure_capability uses cache for confirmed installs"""
        # Add to cache
        manager._installed_capabilities.add("pandas")
        
        # Should return True without checking
        with patch.object(manager, '_check_module_installed') as mock_check:
            result = manager.ensure_capability("pandas")
            
            assert result is True
            mock_check.assert_not_called()

    @patch('subprocess.run')
    def test_ensure_capability_installs_missing(self, mock_run, manager):
        """Test ensure_capability installs missing package"""
        # Mock installation success
        mock_run.return_value = Mock(returncode=0, stdout="Installed", stderr="")
        
        # Mock module not found initially, then found after install
        with patch.object(manager, '_check_module_installed', side_effect=[False, True]):
            result = manager.ensure_capability("pandas")
            
            assert result is True
            assert "pandas" in manager._installed_capabilities

    @patch('subprocess.run')
    def test_ensure_capability_install_fails(self, mock_run, manager):
        """Test ensure_capability when installation fails"""
        # Mock installation failure
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error")
        
        # Mock module not found
        with patch.object(manager, '_check_module_installed', return_value=False):
            result = manager.ensure_capability("pandas")
            
            assert result is False
            assert "pandas" not in manager._installed_capabilities

    def test_capability_packages_mapping(self, manager):
        """Test that capability package mapping works correctly"""
        # Test specific mappings
        assert manager.CAPABILITY_PACKAGES["pandas"] == "pandas"
        assert manager.CAPABILITY_PACKAGES["opencv"] == "opencv-python"
        assert manager.CAPABILITY_PACKAGES["cv2"] == "opencv-python"
        assert manager.CAPABILITY_PACKAGES["playwright"] == "playwright"
        assert manager.CAPABILITY_PACKAGES["bs4"] == "beautifulsoup4"

    @patch('subprocess.run')
    def test_ensure_capability_uses_correct_package_name(self, mock_run, manager):
        """Test that ensure_capability uses the mapped package name"""
        # Mock installation success
        mock_run.return_value = Mock(returncode=0, stdout="Installed", stderr="")
        
        # Mock module not found initially, then found after install
        with patch.object(manager, '_check_module_installed', side_effect=[False, True]):
            manager.ensure_capability("opencv")
            
            # Check that opencv-python was installed, not opencv
            call_args = mock_run.call_args[0][0]
            assert "opencv-python" in call_args

    def test_capability_name_normalization(self, manager):
        """Test that capability names are normalized to lowercase"""
        with patch.object(manager, '_check_module_installed', return_value=True):
            manager.ensure_capability("PANDAS")
            assert "pandas" in manager._installed_capabilities

    @patch('subprocess.run')
    def test_ensure_capability_verifies_after_install(self, mock_run, manager):
        """Test that ensure_capability verifies module after installation"""
        # Mock successful installation
        mock_run.return_value = Mock(returncode=0, stdout="Installed", stderr="")
        
        # Module not found before install, still not found after (installation problem)
        with patch.object(manager, '_check_module_installed', return_value=False):
            result = manager.ensure_capability("broken-package")
            
            # Should fail because verification failed
            assert result is False
            assert "broken-package" not in manager._installed_capabilities
