# -*- coding: utf-8 -*-
"""FastAPI Server for Headless Control Interface"""

import logging

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.openapi.docs import get_swagger_ui_html

from app.adapters.infrastructure.api_models import (
    CommandHistoryItem,
    ExecuteRequest,
    ExecuteResponse,
    HistoryResponse,
    StatusResponse,
    TaskResponse,
    Token,
    TokenData,
    User,
)
from app.adapters.infrastructure.auth_adapter import AuthAdapter
from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter
from app.application.services import AssistantService
from app.core.config import settings

logger = logging.getLogger(__name__)

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Initialize authentication adapter
auth_adapter = AuthAdapter()


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


def create_api_server(assistant_service: AssistantService) -> FastAPI:
    """
    Create and configure the FastAPI application

    Args:
        assistant_service: Injected AssistantService instance

    Returns:
        Configured FastAPI application
    """
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

        Args:
            request: Command execution request
            current_user: Current authenticated user

        Returns:
            Command execution response
        """
        try:
            logger.info(f"User '{current_user.username}' executing command via API: {request.command}")
            response = assistant_service.process_command(request.command)

            return ExecuteResponse(
                success=response.success,
                message=response.message,
                data=response.data,
                error=response.error,
            )
        except Exception as e:
            logger.error(f"Error executing command: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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
    
    # Override the default Swagger UI to inject custom JavaScript for password visibility toggle
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html() -> HTMLResponse:
        """Custom Swagger UI with password visibility toggle"""
        swagger_ui_html = get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=app.title + " - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
            swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
            swagger_ui_parameters=swagger_ui_parameters,
        )
        
        # Inject custom JavaScript for password visibility toggle
        custom_js = """
        <script>
        window.addEventListener('load', function() {
            // Wait for Swagger UI to load
            setTimeout(function() {
                // Find all password input fields and add toggle button
                const observer = new MutationObserver(function(mutations) {
                    document.querySelectorAll('input[type="password"]').forEach(function(input) {
                        if (!input.hasAttribute('data-toggle-added')) {
                            input.setAttribute('data-toggle-added', 'true');
                            
                            // Create toggle button
                            const toggleBtn = document.createElement('button');
                            toggleBtn.type = 'button';
                            toggleBtn.innerHTML = '👁️';
                            toggleBtn.style.cssText = 'margin-left: 5px; cursor: pointer; background: #f0f0f0; border: 1px solid #ccc; border-radius: 3px; padding: 2px 8px;';
                            toggleBtn.title = 'Toggle password visibility';
                            
                            // Toggle functionality
                            toggleBtn.onclick = function() {
                                if (input.type === 'password') {
                                    input.type = 'text';
                                    toggleBtn.innerHTML = '🙈';
                                } else {
                                    input.type = 'password';
                                    toggleBtn.innerHTML = '👁️';
                                }
                            };
                            
                            // Insert button after input
                            input.parentNode.insertBefore(toggleBtn, input.nextSibling);
                        }
                    });
                });
                
                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });
            }, 1000);
        });
        </script>
        """
        
        # Get the HTML body and inject the custom script before closing body tag
        html_content = swagger_ui_html.body.decode('utf-8')
        html_content = html_content.replace('</body>', custom_js + '\n</body>')
        
        return HTMLResponse(content=html_content)

    return app
