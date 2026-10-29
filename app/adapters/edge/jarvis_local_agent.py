from app.core.nexus import NexusComponent
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JARVIS Local Agent - Local Bridge Client

This script connects your local Windows/Mac computer to JARVIS in the cloud,
enabling JARVIS to delegate GUI tasks to your local machine.

Features:
- PyAutoGUI automation (click, type, screenshot)
- Browser automation (open_url)
- Security layer with API_KEY_LOCAL verification
- WebSocket connection to JARVIS cloud instance

Usage:
    python jarvis_local_agent.py

Configuration:
    Create a .env file with:
    - JARVIS_WS_URL: WebSocket URL (e.g., ws://localhost:8000/v1/local-bridge)
    - DEVICE_ID: Unique identifier for this device (e.g., meu_pc_stark)
    - API_KEY_LOCAL: Security key to verify commands from JARVIS
"""

import asyncio
import json
import logging
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.adapters.edge.jarvis_agent_status import tracked_action
from app.adapters.edge.environment_observation_publisher import (
    build_desktop_observations,
    configured_observation_target,
    publish_observation,
)

# Check for required dependencies
try:
    import websockets
except ImportError:
    print("❌ Error: 'websockets' not installed")
    print("Install with: pip install websockets")
    sys.exit(1)

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    print("⚠️  Warning: 'pyautogui' not installed - GUI automation will be disabled")
    print("Install with: pip install pyautogui")

# Optional: load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False
    print("ℹ️  Info: 'python-dotenv' not installed - using environment variables only")
    print("Optional: pip install python-dotenv")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("jarvis_local_agent.log")
    ]
)
logger = logging.getLogger(__name__)


class JarvisLocalAgent(NexusComponent):
    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    """
    JARVIS Local Agent - Connects local PC to JARVIS cloud instance.
    
    Handles WebSocket communication and executes delegated tasks with
    security verification.
    """
    
    def __init__(self, jarvis_url: str, device_id: str, api_key: str):
        """
        Initialize the local agent.
        
        Args:
            jarvis_url: WebSocket URL for JARVIS (e.g., ws://localhost:8000/v1/local-bridge)
            device_id: Unique identifier for this device
            api_key: API key for command verification (must not be empty)
            
        Note:
            The main() function validates that api_key is not empty before
            creating the agent instance. An empty api_key will cause the
            program to exit with an error message.
        """
        parsed = urlsplit(jarvis_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["device_id"] = device_id
        query.setdefault("device_type", "desktop")
        query.setdefault(
            "capabilities",
            "pyautogui,screenshot,visual_templates,screen_observation,screen_stream",
        )
        self.jarvis_url = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
        )
        self._visual_navigator = None
        self.device_id = device_id
        self.api_key = api_key
        self.observation_token = os.getenv("JARVIS_OBSERVATION_TOKEN", "").strip()
        self.observation_api_base_url = configured_observation_target(jarvis_url)
        self.connected = False
        self.screenshots_dir = Path("jarvis_screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)
        
        logger.info(f"Initialized JARVIS Local Agent for device: {device_id}")
    
    def verify_api_key(self, received_key: Optional[str]) -> bool:
        """
        Verify that the received API key matches the local one.
        
        Args:
            received_key: API key sent by JARVIS
            
        Returns:
            True if keys match, False otherwise
        """
        if not received_key:
            logger.warning("No API key provided in command")
            return False
        
        if received_key != self.api_key:
            logger.warning("API key mismatch - command rejected")
            return False
        
        return True
    
    async def _execute_task_untracked(self, task: Dict) -> Dict:
        """
        Execute a task from JARVIS.
        
        Args:
            task: Task definition with action, parameters, and api_key
            
        Returns:
            Task result dictionary
        """
        action = task.get("action")
        params = task.get("parameters", {})
        api_key_received = task.get("api_key")
        
        # Security check: verify API key
        if not self.verify_api_key(api_key_received):
            return {
                "success": False,
                "error": "Unauthorized: Invalid API key"
            }
        
        logger.info(f"Executing task: {action}")
        
        try:
            if action == "click":
                return await self._handle_click(params)
            elif action == "type":
                return await self._handle_type(params)
            elif action == "screenshot":
                return await self._handle_screenshot(params)
            elif action in {
                "observe_screen",
                "watch_screen",
                "run_visual_recipe",
                "visual_recipe",
                "capture_visual_template",
                "save_visual_template",
            }:
                return await self._handle_visual_navigation(action, params)
            elif action == "open_url":
                return await self._handle_open_url(params)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}"
                }
        
        except Exception as e:
            logger.error(f"Task execution error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def execute_task(self, task: Dict) -> Dict:
        """Track one authenticated local-agent task from dispatch through completion."""
        action = str(task.get("action", "unknown task"))
        tracked = tracked_action(f"Agente local: {action}")(self._execute_task_untracked)
        return await tracked(task)

    async def _handle_click(self, params: Dict) -> Dict:
        """Handle mouse click action."""
        if not HAS_PYAUTOGUI:
            return {
                "success": False,
                "error": "PyAutoGUI not available"
            }
        
        x = params.get("x", 0)
        y = params.get("y", 0)
        clicks = params.get("clicks", 1)
        button = params.get("button", "left")
        
        pyautogui.click(x, y, clicks=clicks, button=button)
        
        return {
            "success": True,
            "result": f"Clicked at ({x}, {y}) with {button} button, {clicks} times"
        }
    
    async def _handle_type(self, params: Dict) -> Dict:
        """Handle text typing action."""
        if not HAS_PYAUTOGUI:
            return {
                "success": False,
                "error": "PyAutoGUI not available"
            }
        
        text = params.get("text", "")
        interval = params.get("interval", 0.1)
        
        pyautogui.write(text, interval=interval)
        
        return {
            "success": True,
            "result": f"Typed: {text}"
        }
    
    async def _handle_screenshot(self, params: Dict) -> Dict:
        """Handle screenshot action."""
        if not HAS_PYAUTOGUI:
            return {
                "success": False,
                "error": "PyAutoGUI not available"
            }
        
        filename = params.get("filename", f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        filepath = self.screenshots_dir / filename
        
        screenshot = pyautogui.screenshot()
        screenshot.save(str(filepath))
        
        return {
            "success": True,
            "result": f"Screenshot saved to: {filepath}",
            "filepath": str(filepath)
        }
    
    async def _handle_visual_navigation(self, action: str, params: Dict) -> Dict:
        """Run visual navigation locally and return evidence to the bridge."""
        if not HAS_PYAUTOGUI:
            return {"success": False, "status": "unavailable", "message": "PyAutoGUI not available"}
        try:
            if self._visual_navigator is None:
                from app.adapters.edge.visual_navigation_adapter import VisualNavigationAdapter

                self._visual_navigator = VisualNavigationAdapter(pyautogui_module=pyautogui)
            action_aliases = {"visual_recipe": "run_visual_recipe"}
            return await asyncio.to_thread(
                self._visual_navigator.execute,
                {"action": action_aliases.get(action, action), "params": params},
            )
        except Exception as exc:
            logger.exception("Visual navigation task failed")
            return {"success": False, "status": "error", "message": str(exc)}

    async def _handle_open_url(self, params: Dict) -> Dict:
        """Handle opening URL in browser."""
        url = params.get("url", "")
        
        if not url:
            return {
                "success": False,
                "error": "No URL provided"
            }
        
        # Open URL in default browser
        webbrowser.open(url)
        
        return {
            "success": True,
            "result": f"Opened URL: {url}"
        }
    
    async def connect(self):
        """Connect to JARVIS and handle tasks."""
        logger.info(f"Connecting to JARVIS: {self.jarvis_url}")
        
        try:
            async with websockets.connect(self.jarvis_url) as websocket:
                self.connected = True
                logger.info("✓ Connected to JARVIS!")
                
                # Receive welcome message
                welcome = await websocket.recv()
                welcome_data = json.loads(welcome)
                logger.info(f"JARVIS: {welcome_data.get('message', welcome)}")
                
                # Handle tasks in a loop
                while True:
                    try:
                        # Receive message from JARVIS
                        message = await websocket.recv()
                        data = json.loads(message)
                        
                        msg_type = data.get("type")
                        
                        if msg_type == "task":
                            # Execute task
                            task_id = data.get("task_id")
                            logger.info(f"Received task: {data.get('action')} (ID: {task_id})")
                            
                            # Add api_key to task data for verification
                            task_data = {
                                "action": data.get("action"),
                                "parameters": data.get("parameters", {}),
                                "api_key": data.get("api_key")
                            }
                            
                            result = await self.execute_task(task_data)
                            
                            # Send result back to JARVIS
                            response = {
                                "type": "task_result",
                                "task_id": task_id,
                                "success": result.get("success", False),
                                "result": result.get("result", result),
                                "error": result.get("error"),
                                "timestamp": datetime.now().isoformat()
                            }
                            await websocket.send(json.dumps(response))
                            logger.info(f"Task result sent: {result.get('success')}")
                        
                        elif msg_type == "heartbeat_ack":
                            logger.debug("Heartbeat acknowledged")
                        
                        elif msg_type == "connected":
                            logger.info(f"Connection confirmed: {data.get('message')}")
                        
                        else:
                            logger.warning(f"Unknown message type: {msg_type}")
                    
                    except websockets.exceptions.ConnectionClosed:
                        logger.info("Connection closed by JARVIS")
                        self.connected = False
                        break
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON received: {e}")
                    except Exception as e:
                        logger.error(f"Error handling message: {e}", exc_info=True)
        
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
            self.connected = False
        except Exception as e:
            logger.error(f"Connection error: {e}", exc_info=True)
            self.connected = False
    
    async def _publish_environment_observations(self) -> None:
        """Publish passive local facts while an optional bearer token is configured."""
        while True:
            try:
                observations = await asyncio.to_thread(
                    build_desktop_observations, self.device_id
                )
                for observation in observations:
                    await asyncio.to_thread(
                        publish_observation,
                        self.observation_api_base_url,
                        self.observation_token,
                        observation,
                    )
                logger.debug("Published desktop environment observations")
            except Exception as exc:
                # Do not log payloads, URLs, response bodies, or bearer tokens.
                logger.warning(
                    "Desktop environment observation publish failed (%s)",
                    type(exc).__name__,
                )
            await asyncio.sleep(60)

    async def run_with_reconnect(self, reconnect_delay: int = 5):
        """Reconnect the bridge and run the opt-in observation publisher."""
        publisher_task = None
        if self.observation_token:
            publisher_task = asyncio.create_task(self._publish_environment_observations())
        else:
            logger.info(
                "Environment publishing disabled; set JARVIS_OBSERVATION_TOKEN locally to enable it"
            )
        try:
            while True:
                try:
                    await self.connect()
                except KeyboardInterrupt:
                    logger.info("Shutdown requested by user")
                    break
                except Exception as e:
                    logger.error("Unexpected connection error: %s", type(e).__name__)

                if not self.connected:
                    logger.info("Reconnecting in %s seconds...", reconnect_delay)
                    await asyncio.sleep(reconnect_delay)
        finally:
            if publisher_task is not None:
                publisher_task.cancel()
                await asyncio.gather(publisher_task, return_exceptions=True)

def print_banner():
    """Print startup banner."""
    print("=" * 70)
    print("  ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗")
    print("  ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝")
    print("  ██║███████║██████╔╝██║   ██║██║███████╗")
    print("  ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║")
    print("  ██║██║  ██║██║  ██║ ╚████╔╝ ██║███████║")
    print("  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝")
    print()
    print("  Local Agent - Connecting your PC to JARVIS Cloud")
    print("=" * 70)
    print()


def main():
    """Main entry point."""
    print_banner()
    
    # Configuration
    jarvis_url = os.getenv("JARVIS_WS_URL", "ws://localhost:8000/v1/local-bridge")
    device_id = os.getenv("DEVICE_ID", "meu_pc_stark")
    api_key = os.getenv("API_KEY_LOCAL", "")
    
    # Validate configuration
    if not api_key:
        print("❌ Error: API_KEY_LOCAL not set in environment or .env file")
        print("Please create a .env file with:")
        print("  API_KEY_LOCAL=your_secret_key_here")
        sys.exit(1)
    
    # Check if PyAutoGUI is available
    if not HAS_PYAUTOGUI:
        print("⚠️  PyAutoGUI not available - some features will be disabled")
        print("Install with: pip install pyautogui")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    # Display configuration
    print(f"  Device ID:      {device_id}")
    print(f"  JARVIS URL:     {jarvis_url}")
    print(f"  API Key:        {'*' * len(api_key[:8])}... (configured)")
    print(f"  PyAutoGUI:      {'✓ Available' if HAS_PYAUTOGUI else '✗ Not available'}")
    print(f"  Screenshots:    ./jarvis_screenshots/")
    print("=" * 70)
    print()
    print("Starting connection to JARVIS...")
    print("Press Ctrl+C to stop")
    print()
    
    # Create and run agent
    agent = JarvisLocalAgent(jarvis_url, device_id, api_key)
    
    try:
        asyncio.run(agent.run_with_reconnect())
    except KeyboardInterrupt:
        print("\n")
        print("=" * 70)
        print("  JARVIS Local Agent stopped by user")
        print("=" * 70)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
