# -*- coding: utf-8 -*-
"""Extension Manager Service - Manages extensions and packages using uv"""

import importlib
import logging
import subprocess
import sys
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ExtensionManager:
    """
    Service for managing extensions and installing packages on-demand using uv.
    Provides intelligent package management with pre-warming and background installation support.
    """

    # Installation timeout in seconds (5 minutes)
    INSTALL_TIMEOUT = 300

    # Recommended libraries for data tasks
    RECOMMENDED_LIBRARIES: List[str] = ["pandas", "numpy", "matplotlib"]

    # Mapping of capability names to their package installation names
    CAPABILITY_PACKAGES: Dict[str, str] = {
        "pandas": "pandas",
        "numpy": "numpy",
        "matplotlib": "matplotlib",
        "playwright": "playwright",
        "opencv": "opencv-python",
        "cv2": "opencv-python",  # opencv is imported as cv2
        "requests": "requests",
        "beautifulsoup4": "beautifulsoup4",
        "bs4": "beautifulsoup4",  # beautifulsoup4 is imported as bs4
        "scipy": "scipy",
        "scikit-learn": "scikit-learn",
        "sklearn": "scikit-learn",  # scikit-learn is imported as sklearn
    }

    def __init__(self, use_uv: bool = True):
        """
        Initialize the extension manager

        Args:
            use_uv: Whether to use uv for package installation (default: True)
                   Falls back to pip if uv is not available
        """
        self._installed_capabilities: Set[str] = set()
        self._use_uv = use_uv and self._check_uv_available()
        if not self._use_uv and use_uv:
            logger.warning("uv not available, falling back to pip for package installation")
        logger.info(f"ExtensionManager initialized (using {'uv' if self._use_uv else 'pip'})")

    def _check_uv_available(self) -> bool:
        """
        Check if uv is available in the system

        Returns:
            True if uv is available, False otherwise
        """
        try:
            result = subprocess.run(
                ["uv", "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def install_package(self, package_name: str) -> bool:
        """
        Install a package using uv pip install.
        Checks if the library already exists before installing to avoid redundancy.

        Args:
            package_name: Name of the package to install

        Returns:
            True if package is already installed or installation succeeded, False otherwise
        """
        # Normalize package name to lowercase
        package_name = package_name.lower()

        # Get the actual package name to install
        install_name = self.CAPABILITY_PACKAGES.get(package_name, package_name)

        # Check if already installed
        if self._check_package_installed(package_name):
            logger.info(f"Package '{package_name}' is already installed, skipping redundant installation")
            self._installed_capabilities.add(package_name)
            return True

        # Install the package
        logger.info(f"Installing package '{install_name}' via {'uv' if self._use_uv else 'pip'}...")
        if self._install_package_impl(install_name):
            # Verify installation
            if self._check_package_installed(package_name):
                self._installed_capabilities.add(package_name)
                logger.info(f"✅ Successfully installed new skill (library): '{package_name}'")
                return True
            else:
                logger.error(f"Package '{install_name}' installed but module '{package_name}' still not importable")
                return False
        else:
            logger.error(f"Failed to install '{install_name}'")
            return False

    def _check_package_installed(self, module_name: str) -> bool:
        """
        Check if a package/module can be imported

        Args:
            module_name: Name of the module to check

        Returns:
            True if module can be imported, False otherwise
        """
        # Check if we've already confirmed it's installed
        if module_name in self._installed_capabilities:
            return True

        # Try to import the module
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            return False

    def _install_package_impl(self, package_name: str) -> bool:
        """
        Internal implementation for installing a package

        Args:
            package_name: Name of the package to install

        Returns:
            True if installation succeeded, False otherwise
        """
        try:
            if self._use_uv:
                # Use uv pip install
                result = subprocess.run(
                    ["uv", "pip", "install", package_name],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self.INSTALL_TIMEOUT,
                )
            else:
                # Fallback to pip
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", package_name],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self.INSTALL_TIMEOUT,
                )

            if result.returncode == 0:
                logger.info(f"Successfully installed '{package_name}'")
                logger.debug(f"Installation output: {result.stdout}")
                return True
            else:
                logger.error(f"Failed to install '{package_name}': {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Installation of '{package_name}' timed out")
            return False
        except Exception as e:
            logger.error(f"Error installing '{package_name}': {e}")
            return False

    def is_package_installed(self, package_name: str) -> bool:
        """
        Check if a package is installed without attempting to install it

        Args:
            package_name: Name of the package to check

        Returns:
            True if package is available, False otherwise
        """
        package_name = package_name.lower()
        return self._check_package_installed(package_name)

    def get_installed_capabilities(self) -> Set[str]:
        """
        Get the set of capabilities that have been confirmed as installed

        Returns:
            Set of capability names
        """
        return self._installed_capabilities.copy()

    def ensure_recommended_libraries(self) -> Dict[str, bool]:
        """
        Ensure recommended libraries are installed for data tasks.
        This is used for pre-warming.

        Returns:
            Dictionary mapping library name to installation success status
        """
        results = {}
        for library in self.RECOMMENDED_LIBRARIES:
            if not self.is_package_installed(library):
                logger.info(f"Pre-warming: Installing recommended library '{library}'")
                results[library] = self.install_package(library)
            else:
                logger.debug(f"Recommended library '{library}' already installed")
                results[library] = True
        return results

    def check_and_install_for_data_task(self) -> bool:
        """
        Check if recommended libraries are installed for data tasks.
        If not, automatically install them in the background.

        Returns:
            True if all recommended libraries are available or being installed, False otherwise
        """
        missing_libs = [
            lib for lib in self.RECOMMENDED_LIBRARIES
            if not self.is_package_installed(lib)
        ]

        if missing_libs:
            logger.info(f"Data task detected. Missing recommended libraries: {missing_libs}")
            logger.info("Initiating automatic installation...")
            
            # Install missing libraries
            success = True
            for lib in missing_libs:
                if not self.install_package(lib):
                    success = False
            
            return success
        
        logger.debug("All recommended libraries for data tasks are already installed")
        return True
