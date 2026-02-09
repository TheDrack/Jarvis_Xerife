# -*- coding: utf-8 -*-
"""FastAPI Server for Headless Control Interface"""

import logging

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.openapi.docs import get_swagger_ui_html

from app.adapters.infrastructure import api_models
from app.adapters.infrastructure.api_models import (
    Token,
    User,
    ExecuteRequest,
    ExecuteResponse,
    MessageRequest,
    MessageResponse,
    TaskResponse,
    StatusResponse,
    HistoryResponse,
    CommandHistoryItem,
    InstallPackageRequest,
    InstallPackageResponse,
    PackageStatusResponse,
    PrewarmResponse,
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    DeviceResponse,
    DeviceListResponse,
    CommandResultRequest,
    CommandResultResponse,
    DeviceStatusUpdate,
    CapabilityModel,
    ThoughtLogRequest,
    ThoughtLogResponse,
    ThoughtLogListResponse,
    GitHubWorkerRequest,
    GitHubWorkerResponse,
)
from app.adapters.infrastructure.auth_adapter import AuthAdapter
from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter
from app.application.services import AssistantService, ExtensionManager
from app.application.services.device_service import DeviceService
from app.core.config import settings

logger = logging.getLogger(__name__)

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Initialize authentication adapter
auth_adapter = AuthAdapter()


def should_bypass_jarvis_identifier(request_source: str = None) -> bool:
    """
    Determine if request should bypass Jarvis intent identifier.
    
    GitHub Actions and GitHub Issues are processed directly by AI.
    Only user API requests go through Jarvis intent identification.
    
    Args:
        request_source: Source of the request (from RequestSource enum)
        
    Returns:
        True if should bypass Jarvis identifier, False otherwise
    """
    from app.adapters.infrastructure.api_models import RequestSource
    
    if not request_source:
        return False
    
    # Bypass Jarvis identifier for GitHub-sourced requests
    bypass_sources = {
        RequestSource.GITHUB_ACTIONS.value,
        RequestSource.GITHUB_ISSUE.value,
    }
    
    return request_source in bypass_sources


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    Dependency to get the current authenticated user from JWT token

    Args:
        token: JWT token from Authorization header

    Returns:
        Current user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = auth_adapter.verify_token(token)
    if payload is None:
        raise credentials_exception
    
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
    
    # In production, fetch user from database
    # For now, we'll construct user from token data
    user = User(
        username=username,
        email=payload.get("email"),
        full_name=payload.get("full_name"),
    )
    
    return user


def create_api_server(assistant_service: AssistantService, extension_manager: ExtensionManager = None) -> FastAPI:
    """
    Create and configure the FastAPI application

    Args:
        assistant_service: Injected AssistantService instance
        extension_manager: Optional ExtensionManager instance for package management

    Returns:
        Configured FastAPI application
    """
    # Create ExtensionManager if not provided
    if extension_manager is None:
        extension_manager = ExtensionManager()
    
    # Custom Swagger UI configuration for password visibility toggle
    swagger_ui_parameters = {
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
        # Add custom CSS/JS for password visibility toggle
        "syntaxHighlight.theme": "monokai",
    }
    
    # Disable default docs to use our custom endpoint
    app = FastAPI(
        title=settings.app_name + " API",
        version=settings.version,
        description="Headless control interface for the AI assistant",
        swagger_ui_parameters=swagger_ui_parameters,
        docs_url=None,  # Disable default docs
        redoc_url=None,  # Disable redoc
    )
    
    # Initialize database adapter for distributed mode
    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
    
    # Initialize device service for distributed orchestration
    device_service = DeviceService(engine=db_adapter.engine)

    @app.post("/token", response_model=Token)
    async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
        """
        OAuth2 compatible token login endpoint

        Args:
            form_data: OAuth2 password request form with username and password

        Returns:
            Access token

        Raises:
            HTTPException: If authentication fails
        """
        user = auth_adapter.authenticate_user(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token = auth_adapter.create_access_token(
            data={
                "sub": user["username"],
                "email": user["email"],
                "full_name": user["full_name"],
            }
        )
        
        return Token(access_token=access_token, token_type="bearer")

    @app.post("/v1/execute", response_model=ExecuteResponse)
    async def execute_command(
        request: ExecuteRequest,
        current_user: User = Depends(get_current_user),
    ) -> ExecuteResponse:
        """
        Execute a command and return the result (Protected endpoint)
        
        Supports intelligent routing based on request source:
        - GitHub Actions/Issues: Bypass Jarvis identifier, process directly with AI
        - User API requests: Use Jarvis intent identification
        
        Args:
            request: Command execution request with optional metadata for context-aware routing
            current_user: Current authenticated user

        Returns:
            Command execution response
        """
        try:
            # Determine request source
            request_source = None
            if request.metadata and request.metadata.request_source:
                request_source = request.metadata.request_source.value
            
            # Log with source information
            source_info = f" (source: {request_source})" if request_source else ""
            logger.info(f"User '{current_user.username}' executing command via API{source_info}: {request.command}")
            
            # Check if we should bypass Jarvis identifier
            bypass_identifier = should_bypass_jarvis_identifier(request_source)
            
            if bypass_identifier:
                logger.info("GitHub-sourced request detected - bypassing Jarvis identifier, processing directly with AI")
            
            # Convert metadata to dict if provided
            metadata_dict = None
            if request.metadata:
                metadata_dict = {
                    "source_device_id": request.metadata.source_device_id,
                    "network_id": request.metadata.network_id,
                    "network_type": request.metadata.network_type,
                    "request_source": request_source,
                    "bypass_identifier": bypass_identifier,
                }
            
            # Use async_process_command for proper async handling
            response = await assistant_service.async_process_command(request.command, request_metadata=metadata_dict)

            return ExecuteResponse(
                success=response.success,
                message=response.message,
                data=response.data,
                error=response.error,
            )
        except Exception as e:
            logger.error(f"Error executing command: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @app.post("/v1/message", response_model=MessageResponse)
    async def send_message(
        request: MessageRequest,
        current_user: User = Depends(get_current_user),
    ) -> MessageResponse:
        """
        Send a simple message to the assistant (Protected endpoint)
        
        This is a simplified endpoint that accepts natural language messages
        without requiring users to format complex JSON payloads or specify
        command structures. Perfect for chat-like interactions.

        Args:
            request: Message request with text
            current_user: Current authenticated user

        Returns:
            Message response with the assistant's reply
            
        Example:
            POST /v1/message
            {
                "text": "What's the weather like today?"
            }
        """
        try:
            logger.info(f"User '{current_user.username}' sending message via API: {request.text}")
            
            # Process the message using the assistant service
            response = await assistant_service.async_process_command(request.text)

            return MessageResponse(
                success=response.success,
                response=response.message,
                error=response.error,
            )
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return MessageResponse(
                success=False,
                response="",
                error=f"Internal server error: {str(e)}"
            )

    @app.post("/v1/task", response_model=TaskResponse)
    async def create_task(
        request: ExecuteRequest,
        current_user: User = Depends(get_current_user),
    ) -> TaskResponse:
        """
        Create a task for distributed execution (Protected endpoint)
        
        Saves the command to the database with 'pending' status.
        The worker (worker_pc.py) will pick it up and execute it.

        Args:
            request: Command execution request
            current_user: Current authenticated user

        Returns:
            Task creation response with task ID
        """
        try:
            logger.info(f"User '{current_user.username}' creating task via API: {request.command}")
            
            # Interpret the command to get command_type and parameters
            intent = assistant_service.interpreter.interpret(request.command)
            
            # Save as pending task in database
            task_id = db_adapter.save_pending_command(
                user_input=request.command,
                command_type=intent.command_type.value,
                parameters=intent.parameters,
            )
            
            if task_id is None:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create task in database"
                )
            
            return TaskResponse(
                task_id=task_id,
                status="pending",
                message=f"Task created successfully with ID {task_id}",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating task: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @app.get("/v1/status", response_model=StatusResponse)
    async def get_status() -> StatusResponse:
        """
        Get the current system status

        Returns:
            System status information
        """
        try:
            return StatusResponse(
                app_name=settings.app_name,
                version=settings.version,
                is_active=assistant_service.is_running,
                wake_word=assistant_service.wake_word,
                language=settings.language,
            )
        except Exception as e:
            logger.error(f"Error getting status: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @app.get("/v1/history", response_model=HistoryResponse)
    async def get_history(limit: int = 5) -> HistoryResponse:
        """
        Get recent command history

        Args:
            limit: Maximum number of commands to return (default: 5, max: 50)

        Returns:
            Command history response
        """
        try:
            # Limit to reasonable range
            limit = max(1, min(limit, 50))
            history = assistant_service.get_command_history(limit=limit)

            return HistoryResponse(
                commands=[
                    CommandHistoryItem(
                        command=item["command"],
                        timestamp=item["timestamp"],
                        success=item["success"],
                        message=item["message"],
                    )
                    for item in history
                ],
                total=len(history),
            )
        except Exception as e:
            logger.error(f"Error getting history: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @app.get("/health")
    async def health_check() -> JSONResponse:
        """
        Health check endpoint

        Returns:
            Simple health check response
        """
        return JSONResponse(content={"status": "healthy"})

    # Extension Manager Endpoints

    @app.post("/v1/extensions/install", response_model=InstallPackageResponse)
    async def install_package(
        request: InstallPackageRequest,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
    ) -> InstallPackageResponse:
        """
        Install a package using uv (Protected endpoint)
        
        Installation happens in the background to avoid blocking.
        Heavy libraries won't block Jarvis from responding to other requests.

        Args:
            request: Package installation request
            background_tasks: FastAPI background tasks
            current_user: Current authenticated user

        Returns:
            Package installation response
        """
        try:
            package_name = request.package_name.lower()
            logger.info(f"User '{current_user.username}' requesting package installation: {package_name}")

            # Check if already installed (synchronous check)
            if extension_manager.is_package_installed(package_name):
                return InstallPackageResponse(
                    success=True,
                    message=f"Package '{package_name}' is already installed",
                    package_name=package_name,
                    already_installed=True,
                )

            # Install in background
            background_tasks.add_task(extension_manager.install_package, package_name)
            
            return InstallPackageResponse(
                success=True,
                message=f"Installation of '{package_name}' started in background",
                package_name=package_name,
                already_installed=False,
            )
        except Exception as e:
            logger.error(f"Error in package installation endpoint: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @app.get("/v1/extensions/status/{package_name}", response_model=PackageStatusResponse)
    async def get_package_status(
        package_name: str,
        current_user: User = Depends(get_current_user),
    ) -> PackageStatusResponse:
        """
        Check if a package is installed (Protected endpoint)

        Args:
            package_name: Name of the package to check
            current_user: Current authenticated user

        Returns:
            Package installation status
        """
        try:
            package_name = package_name.lower()
            installed = extension_manager.is_package_installed(package_name)
            
            return PackageStatusResponse(
                package_name=package_name,
                installed=installed,
            )
        except Exception as e:
            logger.error(f"Error checking package status: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @app.post("/v1/extensions/prewarm", response_model=PrewarmResponse)
    async def prewarm_libraries(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
    ) -> PrewarmResponse:
        """
        Pre-warm recommended libraries for data tasks (Protected endpoint)
        
        Installs pandas, numpy, and matplotlib if not already present.
        Installation happens in background to avoid blocking.

        Args:
            background_tasks: FastAPI background tasks
            current_user: Current authenticated user

        Returns:
            Pre-warming result
        """
        try:
            logger.info(f"User '{current_user.username}' requesting pre-warming of recommended libraries")
            
            # Check which libraries need installation
            missing_libs = [
                lib for lib in extension_manager.RECOMMENDED_LIBRARIES
                if not extension_manager.is_package_installed(lib)
            ]
            
            if not missing_libs:
                return PrewarmResponse(
                    message="All recommended libraries are already installed",
                    libraries={lib: True for lib in extension_manager.RECOMMENDED_LIBRARIES},
                    all_installed=True,
                )
            
            # Install missing libraries in background
            background_tasks.add_task(extension_manager.ensure_recommended_libraries)
            
            # Return status showing which are installed and which will be
            status = {
                lib: extension_manager.is_package_installed(lib)
                for lib in extension_manager.RECOMMENDED_LIBRARIES
            }
            
            return PrewarmResponse(
                message=f"Pre-warming started in background for: {', '.join(missing_libs)}",
                libraries=status,
                all_installed=False,
            )
        except Exception as e:
            logger.error(f"Error in pre-warming endpoint: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    # Device Management Endpoints
    
    @app.post("/v1/devices/register", response_model=DeviceRegistrationResponse)
    async def register_device(
        request: DeviceRegistrationRequest,
        current_user: User = Depends(get_current_user),
    ) -> DeviceRegistrationResponse:
        """
        Register a new device or update an existing one (Protected endpoint)
        
        Devices can announce their capabilities to Jarvis, allowing distributed orchestration.
        
        Args:
            request: Device registration request with name, type, and capabilities
            current_user: Current authenticated user
        
        Returns:
            Device registration response with assigned device ID
        """
        try:
            logger.info(f"User '{current_user.username}' registering device: {request.name}")
            
            # Convert capabilities to dict format
            capabilities = [
                {
                    "name": cap.name,
                    "description": cap.description,
                    "metadata": cap.metadata,
                }
                for cap in request.capabilities
            ]
            
            device_id = device_service.register_device(
                name=request.name,
                device_type=request.type,
                capabilities=capabilities,
                network_id=request.network_id,
                network_type=request.network_type,
                lat=request.lat,
                lon=request.lon,
                last_ip=request.last_ip,
            )
            
            if device_id is None:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to register device"
                )
            
            return DeviceRegistrationResponse(
                success=True,
                device_id=device_id,
                message=f"Device '{request.name}' registered successfully with ID {device_id}",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error registering device: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    @app.get("/v1/devices", response_model=DeviceListResponse)
    async def list_devices(
        status: str = None,
        current_user: User = Depends(get_current_user),
    ) -> DeviceListResponse:
        """
        List all registered devices (Protected endpoint)
        
        Args:
            status: Optional status filter (online/offline)
            current_user: Current authenticated user
        
        Returns:
            List of registered devices with their capabilities
        """
        try:
            devices = device_service.list_devices(status_filter=status)
            
            return DeviceListResponse(
                devices=[
                    DeviceResponse(
                        id=device["id"],
                        name=device["name"],
                        type=device["type"],
                        status=device["status"],