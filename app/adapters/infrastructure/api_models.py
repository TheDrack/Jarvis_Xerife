# -*- coding: utf-8 -*-
"""Pydantic models for API request/response validation"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RequestSource(str, Enum):
    """Enumeration of request sources"""
    
    GITHUB_ACTIONS = "github_actions"  # Request from GitHub Actions workflow
    GITHUB_ISSUE = "github_issue"      # Request from GitHub Issue
    USER_API = "user_api"              # User request through API
    JARVIS_INTERNAL = "jarvis_internal" # Internal Jarvis request


class RequestMetadata(BaseModel):
    """Metadata about the request context for location-aware routing"""

    source_device_id: Optional[int] = Field(None, description="ID of the device that sent the command")
    network_id: Optional[str] = Field(None, description="Network identifier (SSID or public IP)")
    network_type: Optional[str] = Field(None, description="Network type (wifi, 4g, 5g, ethernet)")
    # Default to USER_API to ensure requests go through full Jarvis identifier by default
    # Only GitHub Actions/Issues should explicitly set their source to bypass the identifier
    request_source: Optional[RequestSource] = Field(
        RequestSource.USER_API,
        description="Source of the request (github_actions, github_issue, user_api, jarvis_internal)"
    )


class ExecuteRequest(BaseModel):
    """Request model for command execution"""

    command: str = Field(..., description="Command to execute", min_length=1)
    metadata: Optional[RequestMetadata] = Field(None, description="Context metadata for intelligent routing")


class MessageRequest(BaseModel):
    """
    Simplified request model for sending messages to the assistant.
    
    This provides a more user-friendly alternative to ExecuteRequest,
    allowing users to send natural language messages without worrying
    about JSON structure or field names.
    
    Example:
        {
            "text": "What's the weather like today?"
        }
    """
    text: str = Field(..., description="Message text to send to the assistant", min_length=1)


class MessageResponse(BaseModel):
    """
    Response model for message requests.
    
    Returns the assistant's response in a simple, easy-to-parse format.
    """
    success: bool = Field(..., description="Whether the message was processed successfully")
    response: str = Field(..., description="The assistant's response text")
    error: Optional[str] = Field(None, description="Error message if processing failed")


class ExecutionPayload(BaseModel):
    """
    Execution payload containing code and execution configuration.
    
    Used by mission execution endpoints to specify Python code to run
    in ephemeral environments with specific dependencies and lifecycle settings.
    
    Example:
        {
            "code": "import requests\\nresponse = requests.get('https://api.example.com')\\nprint(response.json())",
            "dependencies": ["requests==2.31.0"],
            "keep_alive": false,
            "browser_required": false
        }
    """

    code: str = Field(..., description="Python code to execute", min_length=1)
    dependencies: List[str] = Field(default_factory=list, description="List of Python package dependencies")
    keep_alive: bool = Field(False, description="Whether to persist the environment after execution")
    browser_required: bool = Field(False, description="Whether browser interaction is needed")


class ExecuteResponse(BaseModel):
    """Response model for command execution"""

    success: bool = Field(..., description="Whether the command executed successfully")
    message: str = Field(..., description="Result message")
    data: Optional[Dict[str, Any]] = Field(None, description="Optional response data")
    error: Optional[str] = Field(None, description="Error code if execution failed")
    
    # Self-Healing Orchestrator fields
    is_internal: bool = Field(False, description="Whether this is internal thought or user response")
    thought_process: Optional[str] = Field(None, description="Technical reasoning (for INTERNAL_MONOLOGUE)")
    execution_payload: Optional[ExecutionPayload] = Field(None, description="Code execution payload")


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


# ThoughtLog and Self-Healing Models


class ThoughtLogRequest(BaseModel):
    """Request model for creating a thought log entry"""

    mission_id: str = Field(..., description="Unique mission identifier", min_length=1)
    session_id: str = Field(..., description="Session identifier for grouping thoughts", min_length=1)
    status: str = Field(..., description="Interaction status: user_interaction or internal_monologue")
    thought_process: str = Field(..., description="Technical reasoning", min_length=1)
    problem_description: str = Field(default="", description="What problem is being solved")
    solution_attempt: str = Field(default="", description="What solution was tried")
    success: bool = Field(default=False, description="Did this attempt succeed")
    error_message: str = Field(default="", description="Error if failed")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="Additional context")


class ThoughtLogResponse(BaseModel):
    """Response model for thought log entry"""

    id: int = Field(..., description="Thought log ID")
    mission_id: str = Field(..., description="Mission identifier")
    session_id: str = Field(..., description="Session identifier")
    status: str = Field(..., description="Interaction status")
    thought_process: str = Field(..., description="Technical reasoning")
    problem_description: str = Field(..., description="Problem description")
    solution_attempt: str = Field(..., description="Solution attempt")
    success: bool = Field(..., description="Success flag")
    error_message: str = Field(..., description="Error message")
    retry_count: int = Field(..., description="Number of retries")
    requires_human: bool = Field(..., description="Whether human intervention is needed")
    escalation_reason: str = Field(..., description="Reason for escalation")
    created_at: str = Field(..., description="ISO timestamp")


class ThoughtLogListResponse(BaseModel):
    """Response model for listing thought logs"""

    logs: List[ThoughtLogResponse] = Field(..., description="List of thought logs")
    total: int = Field(..., description="Total number of logs")


class GitHubWorkerRequest(BaseModel):
    """Request model for GitHub worker operations"""

    operation: str = Field(..., description="Operation: create_branch, submit_pr, fetch_ci_status")
    branch_name: Optional[str] = Field(None, description="Branch name for create_branch")
    pr_title: Optional[str] = Field(None, description="PR title for submit_pr")
    pr_body: Optional[str] = Field(None, description="PR body for submit_pr")
    run_id: Optional[int] = Field(None, description="Run ID for fetch_ci_status")


class GitHubWorkerResponse(BaseModel):
    """Response model for GitHub worker operations"""

    success: bool = Field(..., description="Whether operation succeeded")
    message: str = Field(..., description="Result message")
    data: Optional[Dict[str, Any]] = Field(None, description="Operation-specific data")


class JarvisDispatchRequest(BaseModel):
    """Request model for Jarvis repository dispatch"""

    intent: str = Field(..., description="User intent: 'create' or 'fix'", pattern="^(create|fix)$")
    instruction: str = Field(..., description="Detailed instruction for the code change", min_length=1)
    context: Optional[str] = Field(None, description="Additional context or file paths")


class JarvisDispatchResponse(BaseModel):
    """Response model for Jarvis repository dispatch"""

    success: bool = Field(..., description="Whether dispatch was triggered")
    message: str = Field(..., description="Result message")
    workflow_url: Optional[str] = Field(None, description="URL to monitor workflow execution")


# Evolution and Self-Awareness Models


class ChapterProgress(BaseModel):
    """Progress data for a capability chapter"""

    chapter: str = Field(..., description="Chapter name (e.g., CHAPTER_1_IMMEDIATE_FOUNDATION)")
    total: int = Field(..., description="Total capabilities in this chapter")
    complete: int = Field(..., description="Number of complete capabilities")
    partial: int = Field(..., description="Number of partial capabilities")
    nonexistent: int = Field(..., description="Number of nonexistent capabilities")
    progress_percentage: float = Field(..., description="Chapter progress percentage (0-100)")


class EvolutionStatusResponse(BaseModel):
    """Response model for /v1/status/evolution endpoint"""

    overall_progress: float = Field(..., description="Overall evolution progress percentage (0-100)")
    total_capabilities: int = Field(..., description="Total number of capabilities in JARVIS_OBJECTIVES_MAP")
    complete_capabilities: int = Field(..., description="Number of complete capabilities")
    partial_capabilities: int = Field(..., description="Number of partial capabilities")
    nonexistent_capabilities: int = Field(..., description="Number of nonexistent capabilities")
    chapters: List[ChapterProgress] = Field(..., description="Chapter-by-chapter progress breakdown")


class ResourceAlert(BaseModel):
    """Alert for missing resources required by a capability"""

    type: str = Field(..., description="Resource type: environment_variable, library, api, permission")
    name: str = Field(..., description="Name of the missing resource")
    description: str = Field(..., description="Description of what is missing")


class CapabilityRequirements(BaseModel):
    """Technical requirements for a capability"""

    capability_id: int = Field(..., description="Capability ID")
    capability_name: str = Field(..., description="Capability name")
    chapter: str = Field(..., description="Chapter this capability belongs to")
    status: str = Field(..., description="Current status: nonexistent, partial, complete")
    requirements: List[str] = Field(..., description="List of technical requirements")
    libraries: List[str] = Field(..., description="Python libraries needed")
    apis: List[str] = Field(..., description="External APIs needed")
    env_vars: List[str] = Field(..., description="Environment variables needed")
    permissions: List[str] = Field(..., description="Permissions needed")
    blueprint: str = Field(..., description="Technical blueprint for implementation")


class NextEvolutionStepResponse(BaseModel):
    """Response model for next evolution step"""

    capability_id: int = Field(..., description="ID of the next capability to implement")
    capability_name: str = Field(..., description="Name of the capability")
    chapter: str = Field(..., description="Chapter this capability belongs to")
    current_status: str = Field(..., description="Current implementation status")
    blueprint: CapabilityRequirements = Field(..., description="Technical blueprint")
    priority_score: int = Field(..., description="Priority score (lower is higher priority)")
