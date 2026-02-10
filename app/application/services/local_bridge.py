# -*- coding: utf-8 -*-
"""
Local Bridge - WebSocket Service for Local PC Connection

Enables JARVIS (running in the cloud/Render) to delegate GUI tasks to a local PC.
The local PC connects via WebSocket and can execute PyAutoGUI commands.
"""

import asyncio
import json
import logging
from typing import Dict, Optional, Set
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class LocalBridgeManager:
    """
    Manages WebSocket connections from local PCs.
    
    Allows JARVIS to delegate tasks requiring GUI interaction (PyAutoGUI)
    to connected local machines.
    """
    
    def __init__(self):
        """Initialize the local bridge manager."""
        # Connected clients: {device_id: WebSocket}
        self.active_connections: Dict[str, WebSocket] = {}
        
        # Task queue for each device
        self.task_queues: Dict[str, asyncio.Queue] = {}
        
        # Task results
        self.task_results: Dict[str, Dict] = {}
        
        logger.info("LocalBridgeManager initialized")
    
    async def connect(self, websocket: WebSocket, device_id: str):
        """
        Accept a new WebSocket connection from a local PC.
        
        Args:
            websocket: The WebSocket connection
            device_id: Unique identifier for the local PC
        """
        await websocket.accept()
        self.active_connections[device_id] = websocket
        self.task_queues[device_id] = asyncio.Queue()
        
        logger.info(f"Local PC connected: {device_id}")
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": f"Connected to JARVIS. Device ID: {device_id}",
            "timestamp": datetime.now().isoformat()
        })
    
    def disconnect(self, device_id: str):
        """
        Handle disconnection of a local PC.
        
        Args:
            device_id: ID of the disconnected device
        """
        if device_id in self.active_connections:
            del self.active_connections[device_id]
        
        if device_id in self.task_queues:
            del self.task_queues[device_id]
        
        logger.info(f"Local PC disconnected: {device_id}")
    
    async def send_task(self, device_id: str, task: Dict) -> Dict:
        """
        Send a task to a connected local PC.
        
        Args:
            device_id: ID of the target device
            task: Task definition dictionary with 'action' and 'parameters'
            
        Returns:
            Task result from the local PC
        """
        if device_id not in self.active_connections:
            return {
                "success": False,
                "error": f"Device {device_id} not connected"
            }
        
        websocket = self.active_connections[device_id]
        task_id = f"{device_id}_{datetime.now().timestamp()}"
        
        # Send task to local PC
        task_message = {
            "type": "task",
            "task_id": task_id,
            "action": task.get("action"),
            "parameters": task.get("parameters", {}),
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            await websocket.send_json(task_message)
            logger.info(f"Task sent to {device_id}: {task.get('action')}")
            
            # Wait for result (with timeout)
            result = await asyncio.wait_for(
                self._wait_for_result(device_id, task_id),
                timeout=30.0
            )
            
            return result
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Task timeout - no response from local PC"
            }
        except Exception as e:
            logger.error(f"Error sending task to {device_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _wait_for_result(self, device_id: str, task_id: str) -> Dict:
        """
        Wait for a task result from the local PC.
        
        Args:
            device_id: Device ID
            task_id: Task ID to wait for
            
        Returns:
            Task result
        """
        # This is a simplified version - in production, use asyncio.Event or similar
        # for better synchronization
        while task_id not in self.task_results:
            await asyncio.sleep(0.1)
        
        result = self.task_results[task_id]
        del self.task_results[task_id]
        return result
    
    async def handle_message(self, device_id: str, message: Dict):
        """
        Handle incoming message from local PC.
        
        Args:
            device_id: Device ID
            message: Message from local PC
        """
        message_type = message.get("type")
        
        if message_type == "task_result":
            # Store task result
            task_id = message.get("task_id")
            self.task_results[task_id] = {
                "success": message.get("success", False),
                "result": message.get("result"),
                "error": message.get("error")
            }
            logger.info(f"Received task result from {device_id}: {task_id}")
        
        elif message_type == "heartbeat":
            # Respond to heartbeat
            websocket = self.active_connections.get(device_id)
            if websocket:
                await websocket.send_json({
                    "type": "heartbeat_ack",
                    "timestamp": datetime.now().isoformat()
                })
        
        elif message_type == "status":
            logger.info(f"Status from {device_id}: {message.get('status')}")
        
        else:
            logger.warning(f"Unknown message type from {device_id}: {message_type}")
    
    def get_connected_devices(self) -> list:
        """
        Get list of connected device IDs.
        
        Returns:
            List of device IDs
        """
        return list(self.active_connections.keys())
    
    def is_device_connected(self, device_id: str) -> bool:
        """
        Check if a device is connected.
        
        Args:
            device_id: Device ID to check
            
        Returns:
            True if connected, False otherwise
        """
        return device_id in self.active_connections


# Global bridge manager instance
_bridge_manager: Optional[LocalBridgeManager] = None


def get_bridge_manager() -> LocalBridgeManager:
    """
    Get the global LocalBridgeManager instance.
    
    Returns:
        The bridge manager
    """
    global _bridge_manager
    
    if _bridge_manager is None:
        _bridge_manager = LocalBridgeManager()
    
    return _bridge_manager
