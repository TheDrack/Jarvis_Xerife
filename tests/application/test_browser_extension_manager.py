# -*- coding: utf-8 -*-
"""Tests for BrowserExtensionManager"""

import shutil
import tempfile
from pathlib import Path

import pytest

from app.application.services.browser_extension_manager import (
    BrowserExtension,
    BrowserExtensionManager,
)


class TestBrowserExtension:
    """Test cases for BrowserExtension model"""
    
    def test_browser_extension_creation(self):
        """Test creating a browser extension"""
        ext = BrowserExtension(
            extension_id="test-ext-001",
            name="Test Extension",
            path=Path("/tmp/test-ext"),
            enabled=True,
            metadata={"version": "1.0"},
        )
        
        assert ext.extension_id == "test-ext-001"
        assert ext.name == "Test Extension"
        assert ext.enabled is True
        assert ext.metadata["version"] == "1.0"
    
    def test_browser_extension_to_dict(self):
        """Test converting extension to dictionary"""
        ext = BrowserExtension(
            extension_id="test-ext-002",
            name="Another Extension",
            path=Path("/tmp/another"),
            enabled=False,
        )
        
        ext_dict = ext.to_dict()
        
        assert ext_dict["extension_id"] == "test-ext-002"
        assert ext_dict["name"] == "Another Extension"
        assert ext_dict["enabled"] is False
        assert ext_dict["metadata"] == {}


class TestBrowserExtensionManager:
    """Test cases for BrowserExtensionManager"""
    
    @pytest.fixture
    def temp_extensions_dir(self):
        """Create a temporary directory for extensions"""
        temp_dir = Path(tempfile.mkdtemp(prefix="test_browser_ext_"))
        yield temp_dir
        # Cleanup
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def extension_manager(self, temp_extensions_dir):
        """Create an extension manager with temporary directory"""
        return BrowserExtensionManager(extensions_dir=temp_extensions_dir)
    
    @pytest.fixture
    def sample_extension_source(self):
        """Create a sample extension source directory"""
        temp_dir = Path(tempfile.mkdtemp(prefix="sample_ext_"))
        
        # Create sample extension files
        manifest = temp_dir / "manifest.json"
        manifest.write_text('{"name": "Sample Extension", "version": "1.0"}')
        
        script = temp_dir / "content.js"
        script.write_text('console.log("Sample extension loaded");')
        
        yield temp_dir
        
        # Cleanup
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_extension_manager_initialization(self, extension_manager):
        """Test that extension manager initializes correctly"""
        assert extension_manager is not None
        assert extension_manager.extensions_dir.exists()
        assert isinstance(extension_manager.extensions, dict)
    
    def test_install_extension(self, extension_manager, sample_extension_source):
        """Test installing a browser extension"""
        result = extension_manager.install_extension(
            extension_id="sample-ext-001",
            name="Sample Extension",
            source_path=sample_extension_source,
            metadata={"author": "Test"},
        )
        
        assert result is True
        
        # Check extension was added
        ext = extension_manager.get_extension("sample-ext-001")
        assert ext is not None
        assert ext.name == "Sample Extension"
        assert ext.enabled is True
        assert ext.metadata["author"] == "Test"
        
        # Check files were copied
        assert ext.path.exists()
        assert (ext.path / "manifest.json").exists()
        assert (ext.path / "content.js").exists()
    
    def test_uninstall_extension(self, extension_manager, sample_extension_source):
        """Test uninstalling a browser extension"""
        # First install
        extension_manager.install_extension(
            extension_id="test-uninstall",
            name="Test Uninstall",
            source_path=sample_extension_source,
        )
        
        # Verify it exists
        assert extension_manager.get_extension("test-uninstall") is not None
        
        # Uninstall
        result = extension_manager.uninstall_extension("test-uninstall")
        assert result is True
        
        # Verify it's gone
        assert extension_manager.get_extension("test-uninstall") is None
    
    def test_enable_disable_extension(self, extension_manager, sample_extension_source):
        """Test enabling and disabling extensions"""
        # Install extension
        extension_manager.install_extension(
            extension_id="toggle-test",
            name="Toggle Test",
            source_path=sample_extension_source,
        )
        
        # Should be enabled by default
        ext = extension_manager.get_extension("toggle-test")
        assert ext.enabled is True
        
        # Disable
        result = extension_manager.disable_extension("toggle-test")
        assert result is True
        ext = extension_manager.get_extension("toggle-test")
        assert ext.enabled is False
        
        # Enable
        result = extension_manager.enable_extension("toggle-test")
        assert result is True
        ext = extension_manager.get_extension("toggle-test")
        assert ext.enabled is True
    
    def test_list_extensions(self, extension_manager, sample_extension_source):
        """Test listing extensions"""
        # Install multiple extensions
        extension_manager.install_extension(
            "ext-1", "Extension 1", sample_extension_source
        )
        extension_manager.install_extension(
            "ext-2", "Extension 2", sample_extension_source
        )
        extension_manager.install_extension(
            "ext-3", "Extension 3", sample_extension_source
        )
        
        # Disable one
        extension_manager.disable_extension("ext-2")
        
        # List all
        all_exts = extension_manager.list_extensions()
        assert len(all_exts) == 3
        
        # List enabled only
        enabled_exts = extension_manager.list_extensions(enabled_only=True)
        assert len(enabled_exts) == 2
        assert all(ext.enabled for ext in enabled_exts)
    
    def test_get_enabled_extension_paths(self, extension_manager, sample_extension_source):
        """Test getting paths to enabled extensions"""
        # Install and configure extensions
        extension_manager.install_extension(
            "enabled-1", "Enabled 1", sample_extension_source
        )
        extension_manager.install_extension(
            "enabled-2", "Enabled 2", sample_extension_source
        )
        extension_manager.install_extension(
            "disabled-1", "Disabled 1", sample_extension_source
        )
        extension_manager.disable_extension("disabled-1")
        
        paths = extension_manager.get_enabled_extension_paths()
        
        assert len(paths) == 2
        assert all(isinstance(p, str) for p in paths)
        assert all("enabled-" in p for p in paths)
    
    def test_get_extension_args_for_chromium(self, extension_manager, sample_extension_source):
        """Test getting Chromium launch arguments"""
        # Install extensions
        extension_manager.install_extension(
            "chrome-ext-1", "Chrome Ext 1", sample_extension_source
        )
        extension_manager.install_extension(
            "chrome-ext-2", "Chrome Ext 2", sample_extension_source
        )
        
        args = extension_manager.get_extension_args_for_chromium()
        
        assert len(args) == 2
        assert any("--load-extension=" in arg for arg in args)
        assert any("--disable-extensions-except=" in arg for arg in args)
    
    def test_get_extension_args_when_no_extensions(self, extension_manager):
        """Test getting args when no extensions are installed"""
        args = extension_manager.get_extension_args_for_chromium()
        assert args == []
    
    def test_get_extension_count(self, extension_manager, sample_extension_source):
        """Test getting extension counts"""
        # Install and configure
        extension_manager.install_extension(
            "count-1", "Count 1", sample_extension_source
        )
        extension_manager.install_extension(
            "count-2", "Count 2", sample_extension_source
        )
        extension_manager.install_extension(
            "count-3", "Count 3", sample_extension_source
        )
        extension_manager.disable_extension("count-3")
        
        counts = extension_manager.get_extension_count()
        
        assert counts["total"] == 3
        assert counts["enabled"] == 2
        assert counts["disabled"] == 1
    
    def test_manifest_persistence(self, temp_extensions_dir, sample_extension_source):
        """Test that extensions persist across manager instances"""
        # Create manager and install extension
        manager1 = BrowserExtensionManager(extensions_dir=temp_extensions_dir)
        manager1.install_extension(
            "persist-test", "Persist Test", sample_extension_source
        )
        
        # Create new manager with same directory
        manager2 = BrowserExtensionManager(extensions_dir=temp_extensions_dir)
        
        # Should load the extension from manifest
        ext = manager2.get_extension("persist-test")
        assert ext is not None
        assert ext.name == "Persist Test"
