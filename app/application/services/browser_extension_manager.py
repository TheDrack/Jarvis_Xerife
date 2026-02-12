# -*- coding: utf-8 -*-
"""BrowserExtensionManager - Manages browser extensions for Playwright automations"""

import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BrowserExtension:
    """Represents a browser extension"""
    
    def __init__(
        self,
        extension_id: str,
        name: str,
        path: Path,
        enabled: bool = True,
        metadata: Optional[Dict] = None
    ):
        self.extension_id = extension_id
        self.name = name
        self.path = Path(path)
        self.enabled = enabled
        self.metadata = metadata or {}
    
    def to_dict(self) -> dict:
        """Convert extension to dictionary"""
        return {
            "extension_id": self.extension_id,
            "name": self.name,
            "path": str(self.path),
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


class BrowserExtensionManager:
    """
    Manages browser extensions for complex Playwright automations
    
    Features:
    - Install and manage browser extensions
    - Enable/disable extensions dynamically
    - Track extension metadata
    - Support for custom automation extensions
    - Integration with Playwright browser contexts
    """
    
    def __init__(self, extensions_dir: Optional[Path] = None):
        """
        Initialize the BrowserExtensionManager
        
        Args:
            extensions_dir: Directory to store extensions
        """
        if extensions_dir:
            self.extensions_dir = Path(extensions_dir)
        else:
            # Use a fixed location in user's home directory
            home_dir = Path.home()
            self.extensions_dir = home_dir / ".jarvis" / "browser_extensions"
        
        self.extensions_dir.mkdir(parents=True, exist_ok=True)
        self.extensions: Dict[str, BrowserExtension] = {}
        
        logger.info(f"BrowserExtensionManager initialized with directory: {self.extensions_dir}")
        
        # Load existing extensions
        self._load_extensions()
    
    def _load_extensions(self) -> None:
        """Load extensions from the extensions directory"""
        try:
            manifest_file = self.extensions_dir / "manifest.json"
            
            if manifest_file.exists():
                with open(manifest_file, 'r') as f:
                    manifest_data = json.load(f)
                    
                for ext_data in manifest_data.get("extensions", []):
                    extension = BrowserExtension(
                        extension_id=ext_data["extension_id"],
                        name=ext_data["name"],
                        path=Path(ext_data["path"]),
                        enabled=ext_data.get("enabled", True),
                        metadata=ext_data.get("metadata", {}),
                    )
                    self.extensions[extension.extension_id] = extension
                    
                logger.info(f"Loaded {len(self.extensions)} browser extensions from manifest")
            else:
                logger.info("No existing browser extensions manifest found")
                
        except Exception as e:
            logger.error(f"Failed to load browser extensions: {e}")
    
    def _save_manifest(self) -> None:
        """Save extensions manifest to disk"""
        try:
            manifest_file = self.extensions_dir / "manifest.json"
            
            manifest_data = {
                "version": "1.0",
                "extensions": [ext.to_dict() for ext in self.extensions.values()],
            }
            
            with open(manifest_file, 'w') as f:
                json.dump(manifest_data, f, indent=2)
                
            logger.debug(f"Saved browser extensions manifest with {len(self.extensions)} extensions")
            
        except Exception as e:
            logger.error(f"Failed to save manifest: {e}")
    
    def install_extension(
        self,
        extension_id: str,
        name: str,
        source_path: Path,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Install a browser extension
        
        Args:
            extension_id: Unique identifier for the extension
            name: Human-readable name
            source_path: Path to the extension source directory
            metadata: Optional metadata about the extension
            
        Returns:
            True if installation succeeded, False otherwise
        """
        try:
            # Create extension directory
            ext_dir = self.extensions_dir / extension_id
            
            if ext_dir.exists():
                logger.warning(f"Browser extension {extension_id} already exists, will overwrite")
                shutil.rmtree(ext_dir)
            
            # Copy extension files
            shutil.copytree(source_path, ext_dir)
            
            # Create extension object
            extension = BrowserExtension(
                extension_id=extension_id,
                name=name,
                path=ext_dir,
                enabled=True,
                metadata=metadata or {},
            )
            
            self.extensions[extension_id] = extension
            self._save_manifest()
            
            logger.info(f"Successfully installed browser extension: {name} ({extension_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to install browser extension {extension_id}: {e}")
            return False
    
    def uninstall_extension(self, extension_id: str) -> bool:
        """
        Uninstall a browser extension
        
        Args:
            extension_id: Extension identifier
            
        Returns:
            True if uninstallation succeeded, False otherwise
        """
        try:
            if extension_id not in self.extensions:
                logger.warning(f"Browser extension {extension_id} not found")
                return False
            
            extension = self.extensions[extension_id]
            
            # Remove extension directory
            if extension.path.exists():
                shutil.rmtree(extension.path)
            
            # Remove from tracking
            del self.extensions[extension_id]
            self._save_manifest()
            
            logger.info(f"Successfully uninstalled browser extension: {extension_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to uninstall browser extension {extension_id}: {e}")
            return False
    
    def enable_extension(self, extension_id: str) -> bool:
        """
        Enable a browser extension
        
        Args:
            extension_id: Extension identifier
            
        Returns:
            True if enabled successfully, False otherwise
        """
        if extension_id not in self.extensions:
            logger.warning(f"Browser extension {extension_id} not found")
            return False
        
        self.extensions[extension_id].enabled = True
        self._save_manifest()
        
        logger.info(f"Enabled browser extension: {extension_id}")
        return True
    
    def disable_extension(self, extension_id: str) -> bool:
        """
        Disable a browser extension
        
        Args:
            extension_id: Extension identifier
            
        Returns:
            True if disabled successfully, False otherwise
        """
        if extension_id not in self.extensions:
            logger.warning(f"Browser extension {extension_id} not found")
            return False
        
        self.extensions[extension_id].enabled = False
        self._save_manifest()
        
        logger.info(f"Disabled browser extension: {extension_id}")
        return True
    
    def get_extension(self, extension_id: str) -> Optional[BrowserExtension]:
        """
        Get a browser extension by ID
        
        Args:
            extension_id: Extension identifier
            
        Returns:
            BrowserExtension if found, None otherwise
        """
        return self.extensions.get(extension_id)
    
    def list_extensions(self, enabled_only: bool = False) -> List[BrowserExtension]:
        """
        List all browser extensions
        
        Args:
            enabled_only: If True, only return enabled extensions
            
        Returns:
            List of BrowserExtension objects
        """
        extensions = list(self.extensions.values())
        
        if enabled_only:
            extensions = [ext for ext in extensions if ext.enabled]
        
        return extensions
    
    def get_enabled_extension_paths(self) -> List[str]:
        """
        Get paths to all enabled extensions for browser launch
        
        Returns:
            List of extension paths as strings for Playwright args
        """
        paths = []
        for ext in self.extensions.values():
            if ext.enabled and ext.path.exists():
                paths.append(str(ext.path))
        
        return paths
    
    def get_extension_args_for_chromium(self) -> List[str]:
        """
        Get Chromium launch arguments for loading enabled extensions
        
        Returns:
            List of arguments to pass to Chromium for loading extensions
        """
        extension_paths = self.get_enabled_extension_paths()
        
        if not extension_paths:
            return []
        
        # Join paths with comma for --load-extension argument
        extensions_arg = f"--load-extension={','.join(extension_paths)}"
        
        return [
            extensions_arg,
            "--disable-extensions-except=" + ','.join(extension_paths),
        ]
    
    def get_extension_count(self) -> Dict[str, int]:
        """
        Get counts of extensions by status
        
        Returns:
            Dictionary with total, enabled, and disabled counts
        """
        total = len(self.extensions)
        enabled = sum(1 for ext in self.extensions.values() if ext.enabled)
        
        return {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
        }
