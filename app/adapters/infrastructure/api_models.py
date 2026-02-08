# -*- coding: utf-8 -*-
"""Pydantic models for API request/response validation"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RequestMetadata(BaseModel):
    """Metadata about the request context for location-aware routing"""

    source_device_id: Optional[int] = Field(None, description="ID of the device that sent the command")
    network_id: Optional[str] = Field(None, description="Network identifier (SSID or public IP)")
    network_type: Optional[str] = Field(None, description="Network type (wifi, 4g, 5g, ethernet)")


class ExecuteRequest(BaseModel):
    """Request model for command execution"""

    command: str = Field(..., description="Command to execute", min_length=1)
    metadata: Optional[RequestMetadata] = Field(None, description="Context metadata for intelligent routing")


class ExecuteResponse(BaseModel):
    """Response model for command execution"""

    success: bool = Field(..., description="Whether the command executed successfully")
    message: str = Field(..., description="Result message")
    data: Optional[Dict[str, Any]] = Field(None, description="Optional response data")
    error: Optional[str] = Field(None, description="Error code if execution failed")


class TaskResponse(BaseModel):
    """Response model for task creation in distributed mode"""

    task_id: int = Field(..., description="ID of the created task")
    status: str = Field(..., description="Task status (pending, completed, failed)")
    message: str = Field(..., description="Status message")


class StatusResponse(BaseModel):
    """Response model for system status"""

    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    is_active: bool = Field(..., description="Whether the AI is active")
    wake_word: str = Field(..., description="Wake word for the assistant")
    language: str = Field(..., description="Language for voice recognition")


class CommandHistoryItem(BaseModel):
    """Single command history item"""

    command: str = Field(..., description="Command that was executed")
    timestamp: str = Field(..., description="ISO timestamp of execution")
    success: bool = Field(..., description="Whether the command succeeded")
    message: str = Field(..., description="Result message")


class HistoryResponse(BaseModel):
    """Response model for command history"""

    commands: List[CommandHistoryItem] = Field(..., description="List of recent commands")
    total: int = Field(..., description="Total number of commands in history")


# Authentication Models


class Token(BaseModel):
    """OAuth2 token response"""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(..., description="Token type (bearer)")


class TokenData(BaseModel):
    """Data encoded in JWT token"""

    username: Optional[str] = Field(None, description="Username from token")


class User(BaseModel):
    """User model"""

    username: str = Field(..., description="Username")
    email: Optional[str] = Field(None, description="User email")
    full_name: Optional[str] = Field(None, description="User full name")
    disabled: Optional[bool] = Field(None, description="Whether user is disabled")


# Extension Manager Models


class InstallPackageRequest(BaseModel):
    """Request model for package installation"""

    package_name: str = Field(..., description="Name of the package to install", min_length=1)


class InstallPackageResponse(BaseModel):
    """Response model for package installation"""

    success: bool = Field(..., description="Whether the installation was successful or package already installed")
    message: str = Field(..., description="Installation result message")
    package_name: str = Field(..., description="Name of the package")
    already_installed: bool = Field(False, description="Whether the package was already installed")


class PackageStatusResponse(BaseModel):
    """Response model for package installation status"""

    package_name: str = Field(..., description="Name of the package")
    installed: bool = Field(..., description="Whether the package is installed")


class PrewarmResponse(BaseModel):
    """Response model for pre-warming recommended libraries"""

    message: str = Field(..., description="Pre-warming result message")
    libraries: Dict[str, bool] = Field(..., description="Map of library names to installation success")
    all_installed: bool = Field(..., description="Whether all recommended libraries were installed")


# Device Management Models


class CapabilityModel(BaseModel):
    """Model for device capability"""

    name: str = Field(..., description="Capability name (e.g., 'camera', 'bluetooth_scan')")
    description: str = Field(default="", description="Capability description")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Technical details as JSON")


class DeviceRegistrationRequest(BaseModel):
    """Request model for device registration"""

    name: str = Field(..., description="Device name", min_length=1)
    type: str = Field(..., description="Device type (mobile, desktop, cloud, iot)")
    capabilities: List[CapabilityModel] = Field(default_factory=list, description="List of device capabilities")
    network_id: Optional[str] = Field(None, description="Network identifier (SSID or public IP)")
    network_type: Optional[str] = Field(None, description="Network type (wifi, 4g, 5g, ethernet)")
    lat: Optional[float] = Field(None, description="Latitude coordinate")
    lon: Optional[float] = Field(None, description="Longitude coordinate")
    last_ip: Optional[str] = Field(None, description="Last known IP address")


class DeviceRegistrationResponse(BaseModel):
    """Response model for device registration"""

    success: bool = Field(..., description="Whether registration was successful")
    device_id: int = Field(..., description="Assigned device ID")
    message: str = Field(..., description="Registration result message")


class DeviceStatusUpdate(BaseModel):
    """Model for updating device status"""

    status: str = Field(..., description="Device status (online/offline)")
    lat: Optional[float] = Field(None, description="Current latitude coordinate")
    lon: Optional[float] = Field(None, description="Current longitude coordinate")
    last_ip: Optional[str] = Field(None, description="Current IP address")


class DeviceResponse(BaseModel):
    """Response model for device information"""

    id: int = Field(..., description="Device ID")
    name: str = Field(..., description="Device name")
    type: str = Field(..., description="Device type")
    status: str = Field(..., description="Device status")
    network_id: Optional[str] = Field(None, description="Network identifier (SSID or public IP)")
    network_type: Optional[str] = Field(None, description="Network type (wifi, 4g, 5g, ethernet)")
    lat: Optional[float] = Field(None, description="Latitude coordinate")
    lon: Optional[float] = Field(None, description="Longitude coordinate")
    last_ip: Optional[str] = Field(None, description="Last known IP address")
    last_seen: str = Field(..., description="Last seen timestamp (ISO format)")
    capabilities: List[CapabilityModel] = Field(default_factory=list, description="Device capabilities")


class DeviceListResponse(BaseModel):
    """Response model for listing devices"""

    devices: List[DeviceResponse] = Field(..., description="List of registered devices")
    total: int = Field(..., description="Total number of devices")


# Command Result Models


class CommandResultRequest(BaseModel):
    """Request model for submitting command execution results"""

    result_data: Dict[str, Any] = Field(..., description="Result data from command execution")
    success: bool = Field(..., description="Whether the command executed successfully")
    message: Optional[str] = Field(None, description="Result message or error description")
    executor_device_id: Optional[int] = Field(None, description="ID of the device that executed the command")


class CommandResultResponse(BaseModel):
    """Response model for command result submission"""

    success: bool = Field(..., description="Whether the result was saved successfully")
    command_id: int = Field(..., description="ID of the command")
    message: str = Field(..., description="Confirmation message")


# Mission Executor Models


class MissionRequest(BaseModel):
    """Request model for mission execution"""

    mission_id: str = Field(..., description="Unique mission identifier", min_length=1)
    code: str = Field(..., description="Python script to execute", min_length=1)
    requirements: List[str] = Field(default_factory=list, description="List of Python package dependencies")
    browser_interaction: bool = Field(False, description="Whether the mission requires Playwright browser")
    keep_alive: bool = Field(False, description="Whether to persist the environment after execution")
    target_device_id: Optional[int] = Field(None, description="Optional target device ID for routing")
    timeout: int = Field(300, description="Maximum execution time in seconds", ge=1, le=3600)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional mission metadata")


class MissionResponse(BaseModel):
    """Response model for mission execution result"""

    mission_id: str = Field(..., description="ID of the executed mission")
    success: bool = Field(..., description="Whether execution was successful")
    stdout: str = Field("", description="Captured standard output")
    stderr: str = Field("", description="Captured standard error")
    exit_code: int = Field(0, description="Exit code of the script")
    execution_time: float = Field(0.0, description="Time taken to execute in seconds")
    error: Optional[str] = Field(None, description="Error message if execution failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional execution metadata")


class RecordAutomationRequest(BaseModel):
    """Request model for starting automation recording"""

    output_file: Optional[str] = Field(None, description="Optional path to save the generated code")


class RecordAutomationResponse(BaseModel):
    """Response model for automation recording"""

    success: bool = Field(..., description="Whether recording started successfully")
    output_file: Optional[str] = Field(None, description="Path where the code will be saved")
    message: str = Field(..., description="Status message")


class BrowserControlRequest(BaseModel):
    """Request model for browser control operations"""

    operation: str = Field(..., description="Operation to perform: start, stop, status")
    port: int = Field(9222, description="CDP port for browser connection", ge=1024, le=65535)


class BrowserControlResponse(BaseModel):
    """Response model for browser control"""

    success: bool = Field(..., description="Whether operation was successful")
    is_running: bool = Field(..., description="Whether browser is currently running")
    cdp_url: Optional[str] = Field(None, description="CDP URL for connecting to browser")
    message: str = Field(..., description="Status message")
