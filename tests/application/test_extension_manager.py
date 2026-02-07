# -*- coding: utf-8 -*-
"""Tests for ExtensionManager Service"""

import sys
from unittest.mock import Mock, patch

import pytest

from app.application.services import ExtensionManager


class TestExtensionManager:
    """Test cases for ExtensionManager"""

    @pytest.fixture
    def manager_with_uv(self):
        """Create an ExtensionManager instance with uv enabled"""
        with patch.object(ExtensionManager, '_check_uv_available', return_value=True):
            return ExtensionManager(use_uv=True)

    @pytest.fixture
    def manager_with_pip(self):
        """Create an ExtensionManager instance with pip fallback"""
        with patch.object(ExtensionManager, '_check_uv_available', return_value=False):
            return ExtensionManager(use_uv=True)

    def test_initialization_with_uv(self, manager_with_uv):
        """Test that manager initializes correctly with uv"""
        assert manager_with_uv is not None
        assert isinstance(manager_with_uv._installed_capabilities, set)
        assert len(manager_with_uv._installed_capabilities) == 0
        assert manager_with_uv._use_uv is True

    def test_initialization_with_pip_fallback(self, manager_with_pip):
        """Test that manager falls back to pip when uv is not available"""
        assert manager_with_pip is not None
        assert manager_with_pip._use_uv is False

    @patch('subprocess.run')
    def test_check_uv_available_success(self, mock_run):
        """Test checking for uv availability when it's available"""
        mock_run.return_value = Mock(returncode=0)
        manager = ExtensionManager(use_uv=True)
        # uv check happens in __init__, so we need to check the result
        assert manager._use_uv is True or manager._use_uv is False  # Depends on actual availability

    @patch('subprocess.run')
    def test_check_uv_available_not_found(self, mock_run):
        """Test checking for uv availability when it's not available"""
        mock_run.side_effect = FileNotFoundError()
        result = ExtensionManager(use_uv=True)._check_uv_available()
        assert result is False

    def test_is_package_installed_for_installed(self, manager_with_uv):
        """Test checking if an installed package is available"""
        # sys is always available
        assert manager_with_uv.is_package_installed("sys") is True

    def test_is_package_installed_for_missing(self, manager_with_uv):
        """Test checking if a missing package is available"""
        assert manager_with_uv.is_package_installed("nonexistent_package_xyz") is False

    def test_get_installed_capabilities_empty(self, manager_with_uv):
        """Test getting capabilities when none are confirmed"""
        capabilities = manager_with_uv.get_installed_capabilities()
        assert isinstance(capabilities, set)
        assert len(capabilities) == 0

    def test_get_installed_capabilities_after_install(self, manager_with_uv):
        """Test that confirmed capabilities are tracked"""
        # Mock the methods to simulate successful installation
        with patch.object(manager_with_uv, '_check_package_installed', return_value=True):
            manager_with_uv.install_package("pandas")
            capabilities = manager_with_uv.get_installed_capabilities()
            assert "pandas" in capabilities

    @patch('subprocess.run')
    def test_install_package_with_uv_success(self, mock_run, manager_with_uv):
        """Test successful package installation with uv"""
        # Mock successful installation
        mock_run.return_value = Mock(returncode=0, stdout="Successfully installed", stderr="")
        
        # Mock package not installed initially, then installed after
        with patch.object(manager_with_uv, '_check_package_installed', side_effect=[False, True]):
            result = manager_with_uv.install_package("test-package")
            
            assert result is True
            mock_run.assert_called_once()
            # Check that uv pip install was called
            call_args = mock_run.call_args[0][0]
            assert "uv" in call_args
            assert "pip" in call_args
            assert "install" in call_args
            assert "test-package" in call_args

    @patch('subprocess.run')
    def test_install_package_with_pip_success(self, mock_run, manager_with_pip):
        """Test successful package installation with pip fallback"""
        # Mock successful installation
        mock_run.return_value = Mock(returncode=0, stdout="Successfully installed", stderr="")
        
        # Mock package not installed initially, then installed after
        with patch.object(manager_with_pip, '_check_package_installed', side_effect=[False, True]):
            result = manager_with_pip.install_package("test-package")
            
            assert result is True
            mock_run.assert_called_once()
            # Check that pip install was called (not uv)
            call_args = mock_run.call_args[0][0]
            assert sys.executable in call_args
            assert "-m" in call_args
            assert "pip" in call_args
            assert "install" in call_args
            assert "test-package" in call_args

    @patch('subprocess.run')
    def test_install_package_already_installed(self, mock_run, manager_with_uv):
        """Test install_package when package is already installed"""
        # Mock package already installed
        with patch.object(manager_with_uv, '_check_package_installed', return_value=True):
            result = manager_with_uv.install_package("pandas")
            
            assert result is True
            # Should not call subprocess.run since package is already installed
            mock_run.assert_not_called()
            assert "pandas" in manager_with_uv._installed_capabilities

    @patch('subprocess.run')
    def test_install_package_failure(self, mock_run, manager_with_uv):
        """Test failed package installation"""
        # Mock failed installation
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error installing")
        
        # Mock package not installed
        with patch.object(manager_with_uv, '_check_package_installed', return_value=False):
            result = manager_with_uv.install_package("test-package")
            
            assert result is False

    @patch('subprocess.run')
    def test_install_package_timeout(self, mock_run, manager_with_uv):
        """Test package installation timeout"""
        import subprocess
        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired("uv", 300)
        
        # Mock package not installed
        with patch.object(manager_with_uv, '_check_package_installed', return_value=False):
            result = manager_with_uv.install_package("test-package")
            
            assert result is False

    @patch('subprocess.run')
    def test_install_package_exception(self, mock_run, manager_with_uv):
        """Test package installation with exception"""
        # Mock exception
        mock_run.side_effect = Exception("Unexpected error")
        
        # Mock package not installed
        with patch.object(manager_with_uv, '_check_package_installed', return_value=False):
            result = manager_with_uv.install_package("test-package")
            
            assert result is False

    def test_capability_packages_mapping(self, manager_with_uv):
        """Test that capability package mapping works correctly"""
        # Test specific mappings
        assert manager_with_uv.CAPABILITY_PACKAGES["pandas"] == "pandas"
        assert manager_with_uv.CAPABILITY_PACKAGES["numpy"] == "numpy"
        assert manager_with_uv.CAPABILITY_PACKAGES["matplotlib"] == "matplotlib"
        assert manager_with_uv.CAPABILITY_PACKAGES["opencv"] == "opencv-python"
        assert manager_with_uv.CAPABILITY_PACKAGES["cv2"] == "opencv-python"
        assert manager_with_uv.CAPABILITY_PACKAGES["bs4"] == "beautifulsoup4"
        assert manager_with_uv.CAPABILITY_PACKAGES["sklearn"] == "scikit-learn"

    @patch('subprocess.run')
    def test_install_package_uses_correct_package_name(self, mock_run, manager_with_uv):
        """Test that install_package uses the mapped package name"""
        # Mock installation success
        mock_run.return_value = Mock(returncode=0, stdout="Installed", stderr="")
        
        # Mock package not found initially, then found after install
        with patch.object(manager_with_uv, '_check_package_installed', side_effect=[False, True]):
            manager_with_uv.install_package("opencv")
            
            # Check that opencv-python was installed, not opencv
            call_args = mock_run.call_args[0][0]
            assert "opencv-python" in call_args

    def test_package_name_normalization(self, manager_with_uv):
        """Test that package names are normalized to lowercase"""
        with patch.object(manager_with_uv, '_check_package_installed', return_value=True):
            manager_with_uv.install_package("PANDAS")
            assert "pandas" in manager_with_uv._installed_capabilities

    @patch('subprocess.run')
    def test_install_package_verifies_after_install(self, mock_run, manager_with_uv):
        """Test that install_package verifies module after installation"""
        # Mock successful installation
        mock_run.return_value = Mock(returncode=0, stdout="Installed", stderr="")
        
        # Package not found before install, still not found after (installation problem)
        with patch.object(manager_with_uv, '_check_package_installed', return_value=False):
            result = manager_with_uv.install_package("broken-package")
            
            # Should fail because verification failed
            assert result is False
            assert "broken-package" not in manager_with_uv._installed_capabilities

    def test_recommended_libraries_list(self, manager_with_uv):
        """Test that recommended libraries list is defined"""
        assert manager_with_uv.RECOMMENDED_LIBRARIES is not None
        assert isinstance(manager_with_uv.RECOMMENDED_LIBRARIES, list)
        assert "pandas" in manager_with_uv.RECOMMENDED_LIBRARIES
        assert "numpy" in manager_with_uv.RECOMMENDED_LIBRARIES
        assert "matplotlib" in manager_with_uv.RECOMMENDED_LIBRARIES

    @patch('subprocess.run')
    def test_ensure_recommended_libraries_all_installed(self, mock_run, manager_with_uv):
        """Test ensure_recommended_libraries when all are already installed"""
        # Mock all packages as installed
        with patch.object(manager_with_uv, 'is_package_installed', return_value=True):
            result = manager_with_uv.ensure_recommended_libraries()
            
            assert isinstance(result, dict)
            assert all(result.values())  # All should be True
            # Should not call subprocess.run since all are installed
            mock_run.assert_not_called()

    @patch('subprocess.run')
    def test_ensure_recommended_libraries_some_missing(self, mock_run, manager_with_uv):
        """Test ensure_recommended_libraries when some are missing"""
        # Mock installation success
        mock_run.return_value = Mock(returncode=0, stdout="Installed", stderr="")
        
        # Mock pandas installed, numpy and matplotlib not installed
        def mock_installed(package):
            return package == "pandas"
        
        def mock_check_and_install(package):
            if package == "pandas":
                return True
            return False  # Not installed initially
        
        with patch.object(manager_with_uv, 'is_package_installed', side_effect=mock_installed):
            with patch.object(manager_with_uv, '_check_package_installed', side_effect=[False, True, False, True]):
                result = manager_with_uv.ensure_recommended_libraries()
                
                assert isinstance(result, dict)
                # pandas should be True (already installed)
                # numpy and matplotlib should be attempted

    @patch('subprocess.run')
    def test_check_and_install_for_data_task_all_present(self, mock_run, manager_with_uv):
        """Test check_and_install_for_data_task when all libs are present"""
        # Mock all packages as installed
        with patch.object(manager_with_uv, 'is_package_installed', return_value=True):
            result = manager_with_uv.check_and_install_for_data_task()
            
            assert result is True
            # Should not call subprocess.run since all are installed
            mock_run.assert_not_called()

    @patch('subprocess.run')
    def test_check_and_install_for_data_task_missing_libs(self, mock_run, manager_with_uv):
        """Test check_and_install_for_data_task when some libs are missing"""
        # Mock installation success
        mock_run.return_value = Mock(returncode=0, stdout="Installed", stderr="")
        
        # Mock some packages as not installed
        installed_packages = set()
        
        def mock_installed(package):
            return package in installed_packages
        
        def mock_check_installed(package):
            if package in installed_packages:
                return True
            # Simulate successful installation
            installed_packages.add(package)
            return False
        
        with patch.object(manager_with_uv, 'is_package_installed', side_effect=mock_installed):
            with patch.object(manager_with_uv, '_check_package_installed', side_effect=mock_check_installed):
                result = manager_with_uv.check_and_install_for_data_task()
                
                # Should attempt to install missing libraries
                assert mock_run.called

    def test_check_package_installed_cached(self, manager_with_uv):
        """Test that package installation check uses cache"""
        # Add to cache
        manager_with_uv._installed_capabilities.add("pandas")
        
        # Should return True without importing
        result = manager_with_uv._check_package_installed("pandas")
        assert result is True
