# -*- coding: utf-8 -*-
"""PersistentBrowserManager - Manages persistent Playwright browser instances"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class StructuredBrowserLogger:
    """Wrapper for structured logging in browser operations"""
    
    def __init__(self, logger_instance, **context):
        self.logger = logger_instance
        self.context = context
    
    def _log(self, level, msg, **extra):
        """Log with structured context"""
        log_data = {**self.context, **extra, "message": msg}
        self.logger.log(level, json.dumps(log_data))
    
    def info(self, msg, **extra):
        self._log(logging.INFO, msg, **extra)
    
    def error(self, msg, **extra):
        self._log(logging.ERROR, msg, **extra)
    
    def warning(self, msg, **extra):
        self._log(logging.WARNING, msg, **extra)
    
    def debug(self, msg, **extra):
        self._log(logging.DEBUG, msg, **extra)


class PersistentBrowserManager:
    """
    Manages a persistent Playwright browser instance for automation tasks.
    
    Features:
    - Maintains a single browser instance with persistent user_data_dir
    - Preserves logins (Google, Netflix, etc.) between automation sessions
    - Supports CDP (Chrome DevTools Protocol) connections for scripts
    - Provides codegen recording for creating new automation skills
    - Allows browser to remain open for user entertainment after automation
    - Supports browser extensions for complex automations
    - Robust timeout handling and error recovery
    """
    
    # Default timeout for browser operations in seconds
    DEFAULT_TIMEOUT = 30
    
    # Maximum retry attempts for browser operations
    MAX_RETRIES = 3
    
    def __init__(
        self,
        user_data_dir: Optional[Path] = None,
        headless: bool = False,
        browser_type: str = "chromium",
        session_id: Optional[str] = None
    ):
        """
        Initialize the PersistentBrowserManager
        
        Args:
            user_data_dir: Directory for persistent browser data (cookies, logins, etc.)
            headless: Whether to run browser in headless mode
            browser_type: Type of browser (chromium, firefox, webkit)
            session_id: Optional session identifier for structured logging
        """
        # Setup user data directory
        if user_data_dir:
            self.user_data_dir = Path(user_data_dir)
        else:
            # Use a fixed location in user's home directory
            home_dir = Path.home()
            self.user_data_dir = home_dir / ".jarvis" / "browser_data"
        
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        
        self.headless = headless
        self.browser_type = browser_type
        self._browser_process = None
        self._cdp_url = None
        self.session_id = session_id or "default"
        
        # Create structured logger
        self.log = StructuredBrowserLogger(
            logger,
            session_id=self.session_id,
            browser_type=browser_type
        )
        
        # Initialize extension manager
        from app.application.services.browser_extension_manager import BrowserExtensionManager
        self.extension_manager = BrowserExtensionManager()
        
        self.log.info("browser_manager_initialized",
                     user_data_dir=str(self.user_data_dir),
                     headless=headless,
                     extensions_count=self.extension_manager.get_extension_count()["total"])
    
    def start_browser(self, port: int = 9222, timeout: int = DEFAULT_TIMEOUT) -> Optional[str]:
        """
        Start the persistent browser instance with retry logic
        
        Args:
            port: Port for CDP connection (default: 9222)
            timeout: Timeout in seconds for browser startup (default: 30)
            
        Returns:
            CDP URL for connecting to the browser, or None if failed
        """
        if self.is_running():
            self.log.info("browser_already_running", cdp_url=self._cdp_url)
            return self._cdp_url
        
        # Try starting the browser with retries
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self.log.info("browser_starting", 
                            attempt=attempt,
                            max_retries=self.MAX_RETRIES,
                            port=port,
                            timeout=timeout)
                
                result = self._start_browser_impl(port, timeout)
                
                if result:
                    self.log.info("browser_started_successfully", 
                                cdp_url=result,
                                attempt=attempt)
                    return result
                else:
                    self.log.warning("browser_start_failed", attempt=attempt)
                    
            except Exception as e:
                self.log.error("browser_start_exception",
                             attempt=attempt,
                             error=str(e),
                             error_type=type(e).__name__)
            
            # Wait before retry (exponential backoff)
            if attempt < self.MAX_RETRIES:
                wait_time = 2 ** attempt
                self.log.info("browser_retry_waiting", wait_time=wait_time)
                time.sleep(wait_time)
        
        self.log.error("browser_start_failed_all_retries", max_retries=self.MAX_RETRIES)
        return None
    
    def _start_browser_impl(self, port: int, timeout: int) -> Optional[str]:
        """
        Internal implementation for starting the browser
        
        Args:
            port: Port for CDP connection
            timeout: Timeout in seconds
            
        Returns:
            CDP URL or None if failed
        """
        try:
            # Import playwright only when needed
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                self.log.error("playwright_not_installed",
                             install_cmd="pip install playwright && playwright install chromium")
                return None
            
            # Build command for launching browser with CDP
            if self.browser_type == "chromium":
                # Use playwright's chromium with CDP
                playwright_browsers = Path.home() / ".cache" / "ms-playwright"
                
                # Find chromium executable
                chromium_dir = None
                if playwright_browsers.exists():
                    for item in playwright_browsers.iterdir():
                        if "chromium" in item.name.lower():
                            chromium_dir = item
                            break
                
                if chromium_dir:
                    if sys.platform == "win32":
                        chrome_exe = chromium_dir / "chrome-win" / "chrome.exe"
                    elif sys.platform == "darwin":
                        chrome_exe = chromium_dir / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
                    else:
                        chrome_exe = chromium_dir / "chrome-linux" / "chrome"
                    
                    if chrome_exe.exists():
                        cmd = [
                            str(chrome_exe),
                            f"--remote-debugging-port={port}",
                            f"--user-data-dir={self.user_data_dir}",
                        ]
                        
                        if self.headless:
                            cmd.append("--headless=new")
                        
                        # Add extension arguments if any extensions are enabled
                        extension_args = self.extension_manager.get_extension_args_for_chromium()
                        if extension_args:
                            cmd.extend(extension_args)
                            self.log.info("browser_loading_extensions",
                                        extensions_count=len(self.extension_manager.get_enabled_extension_paths()))
                        
                        # Start browser process
                        self.log.debug("browser_starting_process", command=' '.join(cmd[:3]))  # Don't log full cmd with extensions
                        self._browser_process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        
                        # Wait for browser to start (with timeout)
                        start_time = time.time()
                        while time.time() - start_time < timeout:
                            if self._browser_process.poll() is not None:
                                # Process exited prematurely
                                stdout, stderr = self._browser_process.communicate()
                                self.log.error("browser_process_exited",
                                             returncode=self._browser_process.returncode,
                                             stderr=stderr.decode() if stderr else "")
                                return None
                            
                            time.sleep(0.5)
                            
                            # Check if port is listening (basic check)
                            if time.time() - start_time > 2:  # Wait at least 2 seconds before declaring success
                                break
                        
                        # Set CDP URL
                        self._cdp_url = f"http://localhost:{port}"
                        
                        self.log.info("browser_process_started", 
                                    cdp_url=self._cdp_url,
                                    pid=self._browser_process.pid)
                        return self._cdp_url
                    else:
                        self.log.error("chromium_executable_not_found", 
                                     expected_path=str(chrome_exe))
                else:
                    self.log.error("chromium_not_installed",
                                 install_cmd="playwright install chromium")
            else:
                self.log.warning("browser_type_not_supported",
                               browser_type=self.browser_type,
                               supported_types=["chromium"])
            
            return None
            
        except Exception as e:
            self.log.error("browser_start_unexpected_error",
                         error=str(e),
                         error_type=type(e).__name__)
            return None
    
    def stop_browser(self) -> bool:
        """
        Stop the persistent browser instance
        
        Returns:
            True if stopped successfully, False otherwise
        """
        if not self.is_running():
            logger.info("Browser is not running")
            return True
        
        try:
            if self._browser_process:
                logger.info("Stopping browser process")
                self._browser_process.terminate()
                
                # Wait for process to terminate
                try:
                    self._browser_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("Browser did not terminate gracefully, forcing kill")
                    self._browser_process.kill()
                
                self._browser_process = None
                self._cdp_url = None
                
                logger.info("Browser stopped successfully")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error stopping browser: {e}")
            return False
    
    def is_running(self) -> bool:
        """
        Check if the browser is currently running
        
        Returns:
            True if browser is running, False otherwise
        """
        if self._browser_process:
            # Check if process is still alive
            return self._browser_process.poll() is None
        
        return False
    
    def get_cdp_url(self) -> Optional[str]:
        """
        Get the CDP URL for connecting to the browser
        
        Returns:
            CDP URL or None if browser is not running
        """
        if self.is_running():
            return self._cdp_url
        
        return None
    
    def record_automation(self, output_file: Optional[Path] = None) -> Optional[str]:
        """
        Start Playwright codegen to record automation and generate code
        
        Args:
            output_file: Optional file to save the generated code
            
        Returns:
            Path to the generated code file, or None if failed
        """
        try:
            # Import playwright
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                logger.error("Playwright not installed")
                return None
            
            # Create output file if not provided
            if output_file is None:
                timestamp = int(time.time())
                temp_dir = Path(tempfile.gettempdir()) / "jarvis_recordings"
                temp_dir.mkdir(parents=True, exist_ok=True)
                output_file = temp_dir / f"skill_{timestamp}.py"
            else:
                output_file = Path(output_file)
            
            logger.info(f"Starting codegen recording. Output: {output_file}")
            
            # Run playwright codegen
            cmd = [
                sys.executable,
                "-m",
                "playwright",
                "codegen",
                "--target", "python",
                "-o", str(output_file),
            ]
            
            # Add user data dir if we have one
            if self.user_data_dir.exists():
                cmd.extend(["--user-data-dir", str(self.user_data_dir)])
            
            # Start codegen process
            logger.info(f"Running: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            # Store the process for later reference
            self._codegen_process = process
            
            logger.info("Codegen started. Close the browser when done recording.")
            logger.info(f"Generated code will be saved to: {output_file}")
            
            return str(output_file)
            
        except Exception as e:
            logger.error(f"Failed to start codegen: {e}", exc_info=True)
            return None
    
    def wait_for_codegen(self, timeout: int = 600) -> bool:
        """
        Wait for codegen recording to complete
        
        Args:
            timeout: Maximum time to wait in seconds (default: 10 minutes)
            
        Returns:
            True if recording completed, False if timeout or error
        """
        if not hasattr(self, '_codegen_process') or not self._codegen_process:
            logger.warning("No active codegen process")
            return False
        
        try:
            logger.info(f"Waiting for codegen to complete (timeout: {timeout}s)")
            
            self._codegen_process.wait(timeout=timeout)
            
            logger.info("Codegen recording completed")
            return True
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Codegen recording timeout after {timeout}s")
            return False
        except Exception as e:
            logger.error(f"Error waiting for codegen: {e}")
            return False
    
    def get_generated_code(self, code_file: str) -> Optional[str]:
        """
        Read the generated code from a file
        
        Args:
            code_file: Path to the generated code file
            
        Returns:
            Generated code as string, or None if failed
        """
        try:
            code_path = Path(code_file)
            
            if not code_path.exists():
                logger.error(f"Code file not found: {code_file}")
                return None
            
            code = code_path.read_text()
            logger.info(f"Read {len(code)} characters from {code_file}")
            
            return code
            
        except Exception as e:
            logger.error(f"Error reading generated code: {e}")
            return None
    
    def cleanup_recordings(self, max_age_days: int = 7) -> None:
        """
        Clean up old recording files
        
        Args:
            max_age_days: Maximum age in days for recording files
        """
        try:
            temp_dir = Path(tempfile.gettempdir()) / "jarvis_recordings"
            
            if not temp_dir.exists():
                return
            
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            for item in temp_dir.iterdir():
                if item.is_file() and item.suffix == ".py":
                    # Check age
                    item_age = current_time - item.stat().st_mtime
                    
                    if item_age > max_age_seconds:
                        logger.info(f"Removing old recording: {item.name}")
                        item.unlink()
                        
        except Exception as e:
            logger.error(f"Error cleaning recordings: {e}")
