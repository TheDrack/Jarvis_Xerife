from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""System commands and automation actions for Jarvis Assistant"""

import logging
import time
import webbrowser as wb
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class SystemCommands(NexusComponent):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    """Handler for system automation and interface control"""

    def __init__(self) -> None:
        """Initialize system commands handler"""
        # Lazy import of pyautogui to reduce startup memory usage
        try:
            import pyautogui
            self._pyautogui = pyautogui
            self._pyautogui_available = True
            pyautogui.PAUSE = settings.pyautogui_pause
        except ImportError:
            self._pyautogui = None
            self._pyautogui_available = False
        
        # Lazy import of pynput to reduce startup memory usage
        try:
            from pynput.keyboard import Controller
            self.keyboard = Controller()
            self._pynput_available = True
        except ImportError:
            self.keyboard = None
            self._pynput_available = False

    def type_text(self, text: str) -> None:
        """
        Type text using keyboard controller

        Args:
            text: Text to type
        """
        if not self._pynput_available:
            logger.warning(f"pynput not available, would type: {text}")
            return
        self.keyboard.type(text)

    def press_key(self, key: str) -> None:
        """
        Press a keyboard key

        Args:
            key: Key name to press
        """
        if not self._pyautogui_available:
            logger.warning(f"PyAutoGUI not available, would press key: {key}")
            return
        self._pyautogui.press(key)

    def press_keys(self, keys: list[str]) -> None:
        """
        Press multiple keys sequentially

        Args:
            keys: List of key names to press
        """
        if not self._pyautogui_available:
            logger.warning(f"PyAutoGUI not available, would press keys: {keys}")
            return
        for key in keys:
            self._pyautogui.press(key)

    def hotkey(self, *keys: str) -> None:
        """
        Press a hotkey combination

        Args:
            keys: Keys to press together
        """
        if not self._pyautogui_available:
            logger.warning(f"PyAutoGUI not available, would press hotkey: {keys}")
            return
        self._pyautogui.hotkey(*keys)

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        """
        Click at specific coordinates

        Args:
            x: X coordinate
            y: Y coordinate
            button: Mouse button ('left', 'right', 'middle')
            clicks: Number of clicks
        """
        if not self._pyautogui_available:
            logger.warning(f"PyAutoGUI not available, would click at ({x}, {y})")
            return
        self._pyautogui.click(x, y, button=button, clicks=clicks)

    def locate_on_screen(
        self, image_path: str, timeout: Optional[float] = None
    ) -> Optional[tuple[int, int]]:
        """
        Locate an image on screen

        Args:
            image_path: Path to image file
            timeout: Maximum time to search (uses default if None)

        Returns:
            Tuple of (x, y) coordinates if found, None otherwise
        """
        if not self._pyautogui_available:
            logger.warning(f"PyAutoGUI not available, would search for image: {image_path}")
            return None
        
        search_timeout = timeout or settings.search_timeout
        attempts = 0
        max_attempts = int(search_timeout * 4)  # Check every 0.25 seconds

        while attempts < max_attempts:
            try:
                location = self._pyautogui.locateCenterOnScreen(image_path)
                if location:
                    self._pyautogui.moveTo(location)
                    print(f"Image {image_path} found at position: {location}")
                    return location
            except Exception as e:
                print(f"Error locating image: {e}")

            time.sleep(0.25)
            attempts += 1

        print(f"Image {image_path} not found")
        return None


class WebNavigator:
    """Handler for web navigation and browser automation"""

    def __init__(self, system_commands: SystemCommands) -> None:
        """
        Initialize web navigator

        Args:
            system_commands: SystemCommands instance for automation
        """
        self.sys_cmd = system_commands

    def open_url(self, url: str) -> None:
        """
        Open URL in default browser

        Args:
            url: URL to open
        """
        wb.open(url)

    def search_on_page(self, search_text: str) -> None:
        """
        Search for text on current page

        Args:
            search_text: Text to search for
        """
        self.sys_cmd.hotkey("ctrl", "f")
        self.sys_cmd.type_text(search_text)

    def click_search_result(self, navigate: str = "enter") -> None:
        """
        Navigate through search results

        Args:
            navigate: 'enter' for next, 'shift+enter' for previous, 'ctrl+enter' to click
        """
        if navigate == "next":
            self.sys_cmd.press_key("enter")
        elif navigate == "previous":
            self.sys_cmd.hotkey("shift", "enter")
        else:
            self.sys_cmd.hotkey("ctrl", "enter")


class CommandProcessor:
    """Process and route voice commands to appropriate actions"""

    def __init__(self, system_commands: SystemCommands, web_navigator: WebNavigator) -> None:
        """
        Initialize command processor

        Args:
            system_commands: SystemCommands instance
            web_navigator: WebNavigator instance
        """
        self.sys_cmd = system_commands
        self.web_nav = web_navigator
        self.commands_map = {
            "escreva": self._handle_type,
            "aperte": self._handle_press,
            "internet": self._handle_internet,
            "site": self._handle_site,
            "clicar em": self._handle_click_on_page,
        }

    def process(self, command: str) -> None:
        """
        Process a voice command

        Args:
            command: Command text to process
        """
        for keyword, handler in self.commands_map.items():
            if keyword in command:
                # Remove keyword from command
                param = command.replace(f"{keyword} ", "").strip()
                handler(param if param else command)
                return

        print(f"Unknown command: {command}")

    def _handle_type(self, text: str) -> None:
        """Handle type command"""
        self.sys_cmd.type_text(text)

    def _handle_press(self, key: str) -> None:
        """Handle press key command"""
        self.sys_cmd.press_key(key)

    def _handle_internet(self, _: str) -> None:
        """Handle open internet command"""
        self.sys_cmd.hotkey("ctrl", "shift", "c")

    def _handle_site(self, url: str) -> None:
        """Handle open site command"""
        if not url.startswith("http"):
            url = f"https://{url}"
        self.web_nav.open_url(url)

    def _handle_click_on_page(self, search_text: str) -> None:
        """Handle click on page element command"""
        self.web_nav.search_on_page(search_text)
