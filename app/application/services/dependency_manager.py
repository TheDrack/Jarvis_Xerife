# -*- coding: utf-8 -*-
"""Dependency Manager Service - On-demand package installation"""

import importlib
import logging
import subprocess
import sys
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DependencyManager:
    """
    Service for managing and installing dependencies on-demand.
    Checks if required libraries are available and installs them if needed.
    """

    # Installation timeout in seconds (5 minutes)
    INSTALL_TIMEOUT = 300

    # Mapping of capability names to their package installation names
    CAPABILITY_PACKAGES: Dict[str, str] = {
        "pandas": "pandas",
        "playwright": "playwright",
        "opencv": "opencv-python",
        "cv2": "opencv-python",  # opencv is imported as cv2
        "numpy": "numpy",
        "requests": "requests",
        "beautifulsoup4": "beautifulsoup4",
        "bs4": "beautifulsoup4",  # beautifulsoup4 is imported as bs4
    }

    def __init__(self):
        """Initialize the dependency manager"""
        self._installed_capabilities: set = set()
        logger.info("DependencyManager initialized")

    def ensure_capability(self, capability_name: str) -> bool:
        """
        Ensure that a capability (library) is available.
        If not present, attempt to install it via pip.

        Args:
            capability_name: Name of the capability/library to ensure

        Returns:
            True if capability is available, False otherwise
        """
        # Normalize capability name to lowercase
        capability_name = capability_name.lower()

        # Check if capability is already confirmed as installed
        if capability_name in self._installed_capabilities:
            logger.debug(f"Capability '{capability_name}' already confirmed as installed")
            return True

        # Get the package name to install
        package_name = self.CAPABILITY_PACKAGES.get(capability_name, capability_name)

        # Try to import the module
        if self._check_module_installed(capability_name):
            self._installed_capabilities.add(capability_name)
            logger.info(f"Capability '{capability_name}' is already installed")
            return True

        # Module not found, attempt to install
        logger.warning(f"Capability '{capability_name}' not found, attempting to install '{package_name}'")
        if self._install_package(package_name):
            # Verify installation
            if self._check_module_installed(capability_name):
                self._installed_capabilities.add(capability_name)
                logger.info(f"Successfully installed and verified '{capability_name}'")
                return True
            else:
                logger.error(f"Package '{package_name}' installed but module '{capability_name}' still not importable")
                return False
        else:
            logger.error(f"Failed to install '{package_name}'")
            return False

    def _check_module_installed(self, module_name: str) -> bool:
        """
        Check if a module can be imported

        Args:
            module_name: Name of the module to check

        Returns:
            True if module can be imported, False otherwise
        """
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            return False

    def _install_package(self, package_name: str) -> bool:
        """
        Install a package using pip

        Args:
            package_name: Name of the package to install

        Returns:
            True if installation succeeded, False otherwise
        """
        try:
            logger.info(f"Installing package '{package_name}' via pip...")
            # Use subprocess to call pip install
            # Use sys.executable to ensure we use the same Python interpreter
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

    def is_capability_available(self, capability_name: str) -> bool:
        """
        Check if a capability is available without attempting to install it

        Args:
            capability_name: Name of the capability to check

        Returns:
            True if capability is available, False otherwise
        """
        capability_name = capability_name.lower()
        if capability_name in self._installed_capabilities:
            return True
        return self._check_module_installed(capability_name)

    def get_installed_capabilities(self) -> set:
        """
        Get the set of capabilities that have been confirmed as installed

        Returns:
            Set of capability names
        """
        return self._installed_capabilities.copy()
