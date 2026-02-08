# -*- coding: utf-8 -*-
"""PersistentBrowserManager - Manages persistent Playwright browser instances"""

import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PersistentBrowserManager:
    """
    Manages a persistent Playwright browser instance for automation tasks.
    
    Features:
    - Maintains a single browser instance with persistent user_data_dir
    - Preserves logins (Google, Netflix, etc.) between automation sessions
    - Supports CDP (Chrome DevTools Protocol) connections for scripts
    - Provides codegen recording for creating new automation skills
    - Allows browser to remain open for user entertainment after automation
    """
    
    def __init__(
        self,
        user_data_dir: Optional[Path] = None,
        headless: bool = False,
        browser_type: str = "chromium"
    ):
        """
        Initialize the PersistentBrowserManager
        
        Args:
            user_data_dir: Directory for persistent browser data (cookies, logins, etc.)
            headless: Whether to run browser in headless mode
            browser_type: Type of browser (chromium, firefox, webkit)
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
        
        logger.info(f"PersistentBrowserManager initialized")
        logger.info(f"User data directory: {self.user_data_dir}")
        logger.info(f"Browser type: {browser_type}, Headless: {headless}")
    
    def start_browser(self, port: int = 9222) -> Optional[str]:
        """
        Start the persistent browser instance
        
        Args:
            port: Port for CDP connection (default: 9222)
            
        Returns:
            CDP URL for connecting to the browser, or None if failed
        """
        if self.is_running():
            logger.info("Browser is already running")
            return self._cdp_url
        
        try:
            # Import playwright only when needed
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                logger.error("Playwright not installed. Install with: pip install playwright")
                logger.error("Then run: playwright install chromium")
                return None
            
            # Start browser with CDP enabled
            logger.info(f"Starting {self.browser_type} browser on port {port}")
            
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
                        
                        # Start browser process
                        self._browser_process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        
                        # Wait for browser to start
                        time.sleep(2)
                        
                        # Set CDP URL
                        self._cdp_url = f"http://localhost:{port}"
                        
                        logger.info(f"Browser started successfully. CDP URL: {self._cdp_url}")
                        return self._cdp_url
                    else:
                        logger.error(f"Chromium executable not found at: {chrome_exe}")
                else:
                    logger.error("Playwright chromium not found. Run: playwright install chromium")
            else:
                logger.warning(f"Browser type {self.browser_type} not fully supported for CDP")
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to start browser: {e}", exc_info=True)
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
