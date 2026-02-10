# -*- coding: utf-8 -*-
"""FastAPI Server for Headless Control Interface"""

import logging
from datetime import datetime
import platform

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse, Response
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
    JarvisDispatchRequest,
    JarvisDispatchResponse,
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

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """
        Root endpoint - Stark Industries command interface
        Serves the main HTML UI for interacting with Jarvis with authentication and voice input
        """
        html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>J.A.R.V.I.S. Command Interface</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Courier New', monospace;
            background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
            color: #00d4ff;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }
        
        .header {
            background: rgba(0, 20, 40, 0.8);
            border-bottom: 2px solid #00d4ff;
            padding: 20px;
            text-align: center;
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.3);
        }
        
        .header h1 {
            font-size: 2.5em;
            text-shadow: 0 0 10px #00d4ff, 0 0 20px #00d4ff;
            letter-spacing: 5px;
            animation: glow 2s ease-in-out infinite alternate;
        }
        
        @keyframes glow {
            from { text-shadow: 0 0 10px #00d4ff, 0 0 20px #00d4ff; }
            to { text-shadow: 0 0 20px #00d4ff, 0 0 30px #00d4ff, 0 0 40px #00d4ff; }
        }
        
        .status {
            display: inline-block;
            margin-top: 10px;
            padding: 5px 15px;
            background: rgba(0, 212, 255, 0.1);
            border: 1px solid #00d4ff;
            border-radius: 20px;
            font-size: 0.9em;
        }
        
        .user-info {
            position: absolute;
            top: 20px;
            right: 20px;
            font-size: 0.9em;
        }
        
        .logout-btn {
            margin-left: 15px;
            background: rgba(255, 0, 0, 0.2);
            border: 1px solid #ff0000;
            border-radius: 5px;
            padding: 5px 10px;
            color: #ff0000;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .logout-btn:hover {
            background: rgba(255, 0, 0, 0.4);
            box-shadow: 0 0 10px rgba(255, 0, 0, 0.5);
        }
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(5px);
        }
        
        .modal.active {
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .modal-content {
            background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
            padding: 40px;
            border: 2px solid #00d4ff;
            border-radius: 10px;
            box-shadow: 0 0 40px rgba(0, 212, 255, 0.5);
            max-width: 400px;
            width: 90%;
        }
        
        .modal-content h2 {
            text-align: center;
            margin-bottom: 30px;
            text-shadow: 0 0 10px #00d4ff;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-size: 0.9em;
            letter-spacing: 1px;
        }
        
        .form-group input {
            width: 100%;
            background: rgba(0, 0, 0, 0.6);
            border: 2px solid #00d4ff;
            border-radius: 5px;
            padding: 12px;
            color: #00d4ff;
            font-family: 'Courier New', monospace;
            font-size: 1em;
            outline: none;
            transition: all 0.3s;
        }
        
        .form-group input:focus {
            border-color: #00ff88;
            box-shadow: 0 0 15px rgba(0, 255, 136, 0.3);
        }
        
        .login-btn {
            width: 100%;
            background: linear-gradient(135deg, #00d4ff 0%, #0088cc 100%);
            border: none;
            border-radius: 5px;
            padding: 15px;
            color: #0a0e27;
            font-weight: bold;
            font-family: 'Courier New', monospace;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 2px;
            transition: all 0.3s;
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.3);
        }
        
        .login-btn:hover {
            background: linear-gradient(135deg, #00ff88 0%, #00cc66 100%);
            box-shadow: 0 0 30px rgba(0, 255, 136, 0.5);
        }
        
        .error-message {
            color: #ff0000;
            text-align: center;
            margin-top: 15px;
            font-size: 0.9em;
        }
        
        .container {
            flex: 1;
            max-width: 1200px;
            width: 100%;
            margin: 0 auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
        }
        
        .terminal {
            flex: 1;
            background: rgba(0, 0, 0, 0.6);
            border: 2px solid #00d4ff;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            overflow-y: auto;
            box-shadow: 0 0 30px rgba(0, 212, 255, 0.2);
            min-height: 400px;
        }
        
        .message {
            margin: 10px 0;
            padding: 10px;
            border-left: 3px solid #00d4ff;
            background: rgba(0, 212, 255, 0.05);
            animation: fadeIn 0.3s ease-in;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message.user {
            border-left-color: #00ff88;
            background: rgba(0, 255, 136, 0.05);
        }
        
        .message.system {
            border-left-color: #ff9500;
            background: rgba(255, 149, 0, 0.05);
        }
        
        .message-label {
            font-weight: bold;
            margin-bottom: 5px;
            text-transform: uppercase;
            font-size: 0.8em;
            letter-spacing: 2px;
        }
        
        .input-area {
            display: flex;
            gap: 10px;
        }
        
        #commandInput {
            flex: 1;
            background: rgba(0, 0, 0, 0.6);
            border: 2px solid #00d4ff;
            border-radius: 5px;
            padding: 15px;
            color: #00d4ff;
            font-family: 'Courier New', monospace;
            font-size: 1em;
            outline: none;
            transition: all 0.3s;
        }
        
        #commandInput:focus {
            border-color: #00ff88;
            box-shadow: 0 0 15px rgba(0, 255, 136, 0.3);
        }
        
        #voiceButton {
            background: rgba(0, 0, 0, 0.6);
            border: 2px solid #00d4ff;
            border-radius: 5px;
            padding: 15px 20px;
            color: #00d4ff;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 1.2em;
        }
        
        #voiceButton:hover {
            border-color: #00ff88;
            box-shadow: 0 0 15px rgba(0, 255, 136, 0.3);
        }
        
        #voiceButton.recording {
            background: rgba(255, 0, 0, 0.3);
            border-color: #ff0000;
            animation: pulse 1s ease-in-out infinite;
        }
        
        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 15px rgba(255, 0, 0, 0.5); }
            50% { box-shadow: 0 0 30px rgba(255, 0, 0, 0.8); }
        }
        
        #sendButton {
            background: linear-gradient(135deg, #00d4ff 0%, #0088cc 100%);
            border: none;
            border-radius: 5px;
            padding: 15px 30px;
            color: #0a0e27;
            font-weight: bold;
            font-family: 'Courier New', monospace;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 2px;
            transition: all 0.3s;
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.3);
        }
        
        #sendButton:hover {
            background: linear-gradient(135deg, #00ff88 0%, #00cc66 100%);
            box-shadow: 0 0 30px rgba(0, 255, 136, 0.5);
            transform: translateY(-2px);
        }
        
        #sendButton:active {
            transform: translateY(0);
        }
        
        #sendButton:disabled {
            background: #333;
            cursor: not-allowed;
            opacity: 0.5;
        }
        
        .loading {
            display: none;
            text-align: center;
            padding: 10px;
            color: #00d4ff;
        }
        
        .loading.active {
            display: block;
        }
        
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(0, 212, 255, 0.3);
            border-radius: 50%;
            border-top-color: #00d4ff;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .hidden {
            display: none !important;
        }
    </style>
</head>
<body>
    <!-- Login Modal -->
    <div id="loginModal" class="modal active">
        <div class="modal-content">
            <h2>J.A.R.V.I.S. ACCESS</h2>
            <form id="loginForm">
                <div class="form-group">
                    <label for="username">USERNAME</label>
                    <input type="text" id="username" name="username" required autocomplete="username">
                </div>
                <div class="form-group">
                    <label for="password">PASSWORD</label>
                    <input type="password" id="password" name="password" required autocomplete="current-password">
                </div>
                <button type="submit" class="login-btn">AUTHENTICATE</button>
                <div id="loginError" class="error-message"></div>
            </form>
        </div>
    </div>
    
    <!-- Main Interface -->
    <div id="mainInterface" class="hidden">
        <div class="header">
            <h1>J.A.R.V.I.S.</h1>
            <div class="status">● SYSTEM ONLINE</div>
            <div class="user-info">
                <span id="userDisplay"></span>
                <button class="logout-btn" id="logoutBtn">LOGOUT</button>
            </div>
        </div>
        
        <div class="container">
            <div class="terminal" id="terminal">
                <div class="message system">
                    <div class="message-label">System</div>
                    <div>J.A.R.V.I.S. Command Interface initialized. Ready for input.</div>
                </div>
            </div>
            
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <span style="margin-left: 10px;">Processing...</span>
            </div>
            
            <div class="input-area">
                <button id="voiceButton" title="Voice Input">🎤</button>
                <input 
                    type="text" 
                    id="commandInput" 
                    placeholder="Enter command or use voice..."
                    autocomplete="off"
                />
                <button id="sendButton">Execute</button>
            </div>
        </div>
    </div>
    
    <script>
        // Authentication management
        const AUTH_TOKEN_KEY = 'jarvis_auth_token';
        const AUTH_USER_KEY = 'jarvis_auth_user';
        const TOKEN_EXPIRY_KEY = 'jarvis_token_expiry';
        const ACTIVITY_TIMEOUT = 30 * 60 * 1000; // 30 minutes
        let lastActivity = Date.now();
        let activityCheckInterval;
        
        // UI Elements
        const loginModal = document.getElementById('loginModal');
        const mainInterface = document.getElementById('mainInterface');
        const loginForm = document.getElementById('loginForm');
        const loginError = document.getElementById('loginError');
        const userDisplay = document.getElementById('userDisplay');
        const logoutBtn = document.getElementById('logoutBtn');
        const terminal = document.getElementById('terminal');
        const commandInput = document.getElementById('commandInput');
        const sendButton = document.getElementById('sendButton');
        const voiceButton = document.getElementById('voiceButton');
        const loading = document.getElementById('loading');
        
        // Voice recognition
        let recognition = null;
        let isRecording = false;
        
        // Initialize Web Speech API
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'pt-BR'; // Portuguese Brazilian
            
            recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                commandInput.value = transcript;
                addMessage(`Voice captured: ${transcript}`, 'system');
            };
            
            recognition.onerror = (event) => {
                console.error('Speech recognition error:', event.error);
                addMessage(`Voice error: ${event.error}`, 'system');
                isRecording = false;
                voiceButton.classList.remove('recording');
            };
            
            recognition.onend = () => {
                isRecording = false;
                voiceButton.classList.remove('recording');
            };
        } else {
            // Hide voice button if not supported
            voiceButton.style.display = 'none';
        }
        
        // Check authentication on load
        function checkAuth() {
            const token = localStorage.getItem(AUTH_TOKEN_KEY);
            const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY);
            
            if (token && expiry && Date.now() < parseInt(expiry)) {
                const user = localStorage.getItem(AUTH_USER_KEY);
                showMainInterface(user);
                startActivityMonitoring();
                return true;
            } else {
                logout();
                return false;
            }
        }
        
        // Login function
        async function login(username, password) {
            try {
                const formData = new URLSearchParams();
                formData.append('username', username);
                formData.append('password', password);
                
                const response = await fetch('/token', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: formData
                });
                
                if (!response.ok) {
                    throw new Error('Invalid credentials');
                }
                
                const data = await response.json();
                
                // Store token and expiry (24 hours)
                localStorage.setItem(AUTH_TOKEN_KEY, data.access_token);
                localStorage.setItem(AUTH_USER_KEY, username);
                localStorage.setItem(TOKEN_EXPIRY_KEY, Date.now() + (24 * 60 * 60 * 1000));
                
                showMainInterface(username);
                startActivityMonitoring();
            } catch (error) {
                loginError.textContent = 'Authentication failed. Please check your credentials.';
                throw error;
            }
        }
        
        // Logout function
        function logout() {
            localStorage.removeItem(AUTH_TOKEN_KEY);
            localStorage.removeItem(AUTH_USER_KEY);
            localStorage.removeItem(TOKEN_EXPIRY_KEY);
            
            if (activityCheckInterval) {
                clearInterval(activityCheckInterval);
            }
            
            loginModal.classList.add('active');
            mainInterface.classList.add('hidden');
            loginError.textContent = '';
        }
        
        // Show main interface
        function showMainInterface(username) {
            userDisplay.textContent = `User: ${username}`;
            loginModal.classList.remove('active');
            mainInterface.classList.remove('hidden');
            commandInput.focus();
        }
        
        // Activity monitoring
        function updateActivity() {
            lastActivity = Date.now();
        }
        
        function checkActivity() {
            const token = localStorage.getItem(AUTH_TOKEN_KEY);
            if (!token) return;
            
            const timeSinceActivity = Date.now() - lastActivity;
            if (timeSinceActivity > ACTIVITY_TIMEOUT) {
                addMessage('Session expired due to inactivity', 'system');
                setTimeout(() => logout(), 2000);
            }
        }
        
        function startActivityMonitoring() {
            // Update activity on user interaction
            ['mousedown', 'keydown', 'scroll', 'touchstart'].forEach(event => {
                document.addEventListener(event, updateActivity);
            });
            
            // Check activity every minute
            activityCheckInterval = setInterval(checkActivity, 60000);
        }
        
        // Login form handler
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            loginError.textContent = '';
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            try {
                await login(username, password);
            } catch (error) {
                console.error('Login error:', error);
            }
        });
        
        // Logout handler
        logoutBtn.addEventListener('click', logout);
        
        // Voice button handler
        if (voiceButton) {
            voiceButton.addEventListener('click', () => {
                if (!recognition) {
                    addMessage('Voice recognition not supported in this browser', 'system');
                    return;
                }
                
                if (isRecording) {
                    recognition.stop();
                    isRecording = false;
                    voiceButton.classList.remove('recording');
                } else {
                    recognition.start();
                    isRecording = true;
                    voiceButton.classList.add('recording');
                    addMessage('Listening... Speak now', 'system');
                }
            });
        }
        
        // Add message to terminal
        function addMessage(text, type = 'system') {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${type}`;
            
            const label = document.createElement('div');
            label.className = 'message-label';
            label.textContent = type === 'user' ? 'User' : type === 'system' ? 'System' : 'J.A.R.V.I.S.';
            
            const content = document.createElement('div');
            content.textContent = text;
            
            messageDiv.appendChild(label);
            messageDiv.appendChild(content);
            terminal.appendChild(messageDiv);
            
            // Auto-scroll to bottom
            terminal.scrollTop = terminal.scrollHeight;
        }
        
        // Send command function
        async function sendCommand() {
            const command = commandInput.value.trim();
            if (!command) return;
            
            const token = localStorage.getItem(AUTH_TOKEN_KEY);
            if (!token) {
                logout();
                return;
            }
            
            // Add user message
            addMessage(command, 'user');
            
            // Clear input
            commandInput.value = '';
            
            // Disable button and show loading
            sendButton.disabled = true;
            loading.classList.add('active');
            
            try {
                const response = await fetch('/v1/execute', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        command: command,
                        source: 'web_ui'
                    })
                });
                
                if (!response.ok) {
                    if (response.status === 401) {
                        addMessage('Session expired. Please login again.', 'system');
                        setTimeout(() => logout(), 2000);
                        return;
                    }
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                
                // Add response
                if (data.result) {
                    addMessage(data.result, 'system');
                } else if (data.response) {
                    addMessage(data.response, 'system');
                } else {
                    addMessage('Command executed successfully', 'system');
                }
                
                updateActivity();
            } catch (error) {
                addMessage(`Error: ${error.message}`, 'system');
                console.error('Error:', error);
            } finally {
                // Re-enable button and hide loading
                sendButton.disabled = false;
                loading.classList.remove('active');
                commandInput.focus();
            }
        }
        
        // Send on button click
        sendButton.addEventListener('click', sendCommand);
        
        // Send on Enter key
        commandInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendCommand();
            }
        });
        
        // Initialize app
        checkAuth();
    </script>
</body>
</html>
        """
        return HTMLResponse(content=html_content)
    
    @app.head("/")
    async def root_head():
        """
        HEAD endpoint for health checks
        Used by monitoring services and browsers to verify server status
        """
        return Response(status_code=200)

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
    async def health_check():
        return {"status": "healthy", "version": "1.0.0"}

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
                        network_id=device.get("network_id"),
                        network_type=device.get("network_type"),
                        lat=device.get("lat"),
                        lon=device.get("lon"),
                        last_ip=device.get("last_ip"),
                        last_seen=device["last_seen"],
                        capabilities=[
                            CapabilityModel(
                                name=cap["name"],
                                description=cap["description"],
                                metadata=cap["metadata"],
                            )
                            for cap in device["capabilities"]
                        ],
                    )
                    for device in devices
                ],
                total=len(devices),
            )
        except Exception as e:
            logger.error(f"Error listing devices: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    @app.get("/v1/devices/{device_id}", response_model=DeviceResponse)
    async def get_device(
        device_id: int,
        current_user: User = Depends(get_current_user),
    ) -> DeviceResponse:
        """
        Get details of a specific device (Protected endpoint)
        
        Args:
            device_id: ID of the device
            current_user: Current authenticated user
        
        Returns:
            Device information with capabilities
        """
        try:
            device = device_service.get_device(device_id)
            
            if device is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Device {device_id} not found"
                )
            
            return DeviceResponse(
                id=device["id"],
                name=device["name"],
                type=device["type"],
                status=device["status"],
                network_id=device.get("network_id"),
                network_type=device.get("network_type"),
                lat=device.get("lat"),
                lon=device.get("lon"),
                last_ip=device.get("last_ip"),
                last_seen=device["last_seen"],
                capabilities=[
                    CapabilityModel(
                        name=cap["name"],
                        description=cap["description"],
                        metadata=cap["metadata"],
                    )
                    for cap in device["capabilities"]
                ],
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting device: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    @app.put("/v1/devices/{device_id}/heartbeat", response_model=DeviceResponse)
    async def device_heartbeat(
        device_id: int,
        status_update: DeviceStatusUpdate,
        current_user: User = Depends(get_current_user),
    ) -> DeviceResponse:
        """
        Update device status and last_seen timestamp (Protected endpoint)
        
        Devices should call this periodically to indicate they are still online.
        
        Args:
            device_id: ID of the device
            status_update: Status update (online/offline)
            current_user: Current authenticated user
        
        Returns:
            Updated device information
        """
        try:
            success = device_service.update_device_status(
                device_id, 
                status_update.status,
                lat=status_update.lat,
                lon=status_update.lon,
                last_ip=status_update.last_ip,
            )
            
            if not success:
                raise HTTPException(
                    status_code=404,
                    detail=f"Device {device_id} not found"
                )
            
            # Get updated device info
            device = device_service.get_device(device_id)
            
            return DeviceResponse(
                id=device["id"],
                name=device["name"],
                type=device["type"],
                status=device["status"],
                network_id=device.get("network_id"),
                network_type=device.get("network_type"),
                lat=device.get("lat"),
                lon=device.get("lon"),
                last_ip=device.get("last_ip"),
                last_seen=device["last_seen"],
                capabilities=[
                    CapabilityModel(
                        name=cap["name"],
                        description=cap["description"],
                        metadata=cap["metadata"],
                    )
                    for cap in device["capabilities"]
                ],
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating device heartbeat: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    # Command Result Endpoint
    
    @app.post("/v1/commands/{command_id}/result", response_model=CommandResultResponse)
    async def submit_command_result(
        command_id: int,
        result: CommandResultRequest,
        current_user: User = Depends(get_current_user),
    ) -> CommandResultResponse:
        """
        Submit command execution result from a device (Protected endpoint)
        
        This implements the feedback loop where devices report back execution results
        (e.g., photo link, music player status, etc.) which can be communicated back to the user.
        
        Args:
            command_id: ID of the command that was executed
            result: Result data from command execution
            current_user: Current authenticated user
        
        Returns:
            Confirmation of result submission
        """
        try:
            import json
            from app.domain.models.device import CommandResult
            from sqlmodel import Session
            
            logger.info(
                f"User '{current_user.username}' submitting result for command {command_id} "
                f"from device {result.executor_device_id}"
            )
            
            # Save the result to the database
            with Session(db_adapter.engine) as session:
                command_result = CommandResult(
                    command_id=command_id,
                    executor_device_id=result.executor_device_id,
                    result_data=json.dumps(result.result_data),
                    success=result.success,
                    message=result.message or "",
                )
                session.add(command_result)
                session.commit()
                session.refresh(command_result)
                
                logger.info(f"Saved command result {command_result.id} for command {command_id}")
            
            # Update the command status if it exists in the interactions table
            if result.success:
                db_adapter.update_command_status(
                    command_id=command_id,
                    status="completed",
                    success=True,
                    response_text=result.message or "Command executed successfully on device",
                )
            else:
                db_adapter.update_command_status(
                    command_id=command_id,
                    status="failed",
                    success=False,
                    response_text=result.message or "Command execution failed on device",
                )
            
            return CommandResultResponse(
                success=True,
                command_id=command_id,
                message=f"Result for command {command_id} saved successfully",
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error submitting command result: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
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

    # Mission Execution Endpoints
    
    @app.post("/v1/missions/execute", response_model=api_models.MissionResponse)
    async def execute_mission(
        request: api_models.MissionRequest,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
    ) -> api_models.MissionResponse:
        """
        Execute a serverless task mission on the Worker (Protected endpoint)
        
        This endpoint allows executing arbitrary Python code with dependencies
        in an isolated environment on the target device.
        
        Args:
            request: Mission execution request
            background_tasks: FastAPI background tasks
            current_user: Current authenticated user
            
        Returns:
            Mission execution result
        """
        try:
            from app.domain.models.mission import Mission
            from app.application.services.task_runner import TaskRunner
            
            logger.info(f"User '{current_user.username}' executing mission: {request.mission_id}")
            
            # Create Mission object
            mission = Mission(
                mission_id=request.mission_id,
                code=request.code,
                requirements=request.requirements,
                browser_interaction=request.browser_interaction,
                keep_alive=request.keep_alive,
                target_device_id=request.target_device_id,
                timeout=request.timeout,
                metadata=request.metadata,
            )
            
            # Initialize TaskRunner
            task_runner = TaskRunner()
            
            # Execute mission
            result = task_runner.execute_mission(mission)
            
            return api_models.MissionResponse(
                mission_id=result.mission_id,
                success=result.success,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                execution_time=result.execution_time,
                error=result.error,
                metadata=result.metadata,
            )
            
        except Exception as e:
            logger.error(f"Error executing mission: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Mission execution failed: {str(e)}")
    
    @app.post("/v1/browser/control", response_model=api_models.BrowserControlResponse)
    async def control_browser(
        request: api_models.BrowserControlRequest,
        current_user: User = Depends(get_current_user),
    ) -> api_models.BrowserControlResponse:
        """
        Control the persistent browser instance (Protected endpoint)
        
        Operations:
        - start: Start the browser with CDP enabled
        - stop: Stop the browser
        - status: Get current browser status
        
        Args:
            request: Browser control request
            current_user: Current authenticated user
            
        Returns:
            Browser control result
        """
        try:
            from app.application.services.browser_manager import PersistentBrowserManager
            
            logger.info(f"User '{current_user.username}' performing browser operation: {request.operation}")
            
            # Initialize browser manager (singleton pattern would be better in production)
            browser_manager = PersistentBrowserManager()
            
            if request.operation == "start":
                cdp_url = browser_manager.start_browser(port=request.port)
                if cdp_url:
                    return api_models.BrowserControlResponse(
                        success=True,
                        is_running=True,
                        cdp_url=cdp_url,
                        message="Browser started successfully",
                    )
                else:
                    return api_models.BrowserControlResponse(
                        success=False,
                        is_running=False,
                        cdp_url=None,
                        message="Failed to start browser",
                    )
            
            elif request.operation == "stop":
                success = browser_manager.stop_browser()
                return api_models.BrowserControlResponse(
                    success=success,
                    is_running=browser_manager.is_running(),
                    cdp_url=None,
                    message="Browser stopped" if success else "Failed to stop browser",
                )
            
            elif request.operation == "status":
                is_running = browser_manager.is_running()
                cdp_url = browser_manager.get_cdp_url() if is_running else None
                return api_models.BrowserControlResponse(
                    success=True,
                    is_running=is_running,
                    cdp_url=cdp_url,
                    message="Browser is running" if is_running else "Browser is not running",
                )
            
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid operation: {request.operation}. Must be 'start', 'stop', or 'status'",
                )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error controlling browser: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Browser control failed: {str(e)}")
    
    @app.post("/v1/browser/record", response_model=api_models.RecordAutomationResponse)
    async def record_automation(
        request: api_models.RecordAutomationRequest,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
    ) -> api_models.RecordAutomationResponse:
        """
        Start recording browser automation with Playwright codegen (Protected endpoint)
        
        This starts the Playwright codegen tool which allows users to interact with
        a browser and automatically generates Python code for those interactions.
        The generated code can be stored as a new "Skill" in the database.
        
        Args:
            request: Recording request with optional output file
            background_tasks: FastAPI background tasks
            current_user: Current authenticated user
            
        Returns:
            Recording start response
        """
        try:
            from app.application.services.browser_manager import PersistentBrowserManager
            from pathlib import Path
            
            logger.info(f"User '{current_user.username}' starting automation recording")
            
            # Initialize browser manager
            browser_manager = PersistentBrowserManager()
            
            # Determine output file
            output_file = None
            if request.output_file:
                output_file = Path(request.output_file)
            
            # Start recording
            output_path = browser_manager.record_automation(output_file=output_file)
            
            if output_path:
                return api_models.RecordAutomationResponse(
                    success=True,
                    output_file=output_path,
                    message="Recording started. Close the browser when done to save the generated code.",
                )
            else:
                return api_models.RecordAutomationResponse(
                    success=False,
                    output_file=None,
                    message="Failed to start recording. Make sure Playwright is installed.",
                )
        
        except Exception as e:
            logger.error(f"Error starting automation recording: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Recording failed: {str(e)}")
    
    # Self-Healing Orchestrator Endpoints
    
    # Initialize ThoughtLog service
    from app.application.services.thought_log_service import ThoughtLogService
    thought_log_service = ThoughtLogService(engine=db_adapter.engine)
    
    @app.post("/v1/thoughts", response_model=api_models.ThoughtLogResponse)
    async def create_thought_log(
        request: api_models.ThoughtLogRequest,
        current_user: User = Depends(get_current_user),
    ) -> api_models.ThoughtLogResponse:
        """
        Create a thought log entry (Protected endpoint)
        
        Args:
            request: Thought log creation request
            current_user: Current authenticated user
            
        Returns:
            Created thought log
        """
        try:
            from app.domain.models.thought_log import InteractionStatus
            
            logger.info(f"User '{current_user.username}' creating thought log for mission {request.mission_id}")
            
            thought = thought_log_service.create_thought(
                mission_id=request.mission_id,
                session_id=request.session_id,
                thought_process=request.thought_process,
                problem_description=request.problem_description,
                solution_attempt=request.solution_attempt,
                status=InteractionStatus(request.status),
                success=request.success,
                error_message=request.error_message,
                context_data=request.context_data,
            )
            
            if thought:
                return api_models.ThoughtLogResponse(
                    id=thought.id,
                    mission_id=thought.mission_id,
                    session_id=thought.session_id,
                    status=thought.status,
                    thought_process=thought.thought_process,
                    problem_description=thought.problem_description,
                    solution_attempt=thought.solution_attempt,
                    success=thought.success,
                    error_message=thought.error_message,
                    retry_count=thought.retry_count,
                    requires_human=thought.requires_human,
                    escalation_reason=thought.escalation_reason,
                    created_at=thought.created_at.isoformat(),
                )
            else:
                raise HTTPException(status_code=500, detail="Failed to create thought log")
                
        except Exception as e:
            logger.error(f"Error creating thought log: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create thought log: {str(e)}")
    
    @app.get("/v1/thoughts/mission/{mission_id}", response_model=api_models.ThoughtLogListResponse)
    async def get_mission_thoughts(
        mission_id: str,
        current_user: User = Depends(get_current_user),
    ) -> api_models.ThoughtLogListResponse:
        """
        Get all thought logs for a specific mission (Protected endpoint)
        
        Args:
            mission_id: Mission identifier
            current_user: Current authenticated user
            
        Returns:
            List of thought logs
        """
        try:
            logger.info(f"User '{current_user.username}' fetching thoughts for mission {mission_id}")
            
            thoughts = thought_log_service.get_mission_thoughts(mission_id)
            
            thought_responses = [
                api_models.ThoughtLogResponse(
                    id=t.id,
                    mission_id=t.mission_id,
                    session_id=t.session_id,
                    status=t.status,
                    thought_process=t.thought_process,
                    problem_description=t.problem_description,
                    solution_attempt=t.solution_attempt,
                    success=t.success,
                    error_message=t.error_message,
                    retry_count=t.retry_count,
                    requires_human=t.requires_human,
                    escalation_reason=t.escalation_reason,
                    created_at=t.created_at.isoformat(),
                )
                for t in thoughts
            ]
            
            return api_models.ThoughtLogListResponse(
                logs=thought_responses,
                total=len(thought_responses),
            )
            
        except Exception as e:
            logger.error(f"Error fetching mission thoughts: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to fetch thoughts: {str(e)}")
    
    @app.get("/v1/thoughts/escalations", response_model=api_models.ThoughtLogListResponse)
    async def get_pending_escalations(
        current_user: User = Depends(get_current_user),
    ) -> api_models.ThoughtLogListResponse:
        """
        Get all missions requiring human intervention (Protected endpoint)
        
        Args:
            current_user: Current authenticated user
            
        Returns:
            List of escalated thought logs
        """
        try:
            logger.info(f"User '{current_user.username}' fetching pending escalations")
            
            escalations = thought_log_service.get_pending_escalations()
            
            thought_responses = [
                api_models.ThoughtLogResponse(
                    id=t.id,
                    mission_id=t.mission_id,
                    session_id=t.session_id,
                    status=t.status,
                    thought_process=t.thought_process,
                    problem_description=t.problem_description,
                    solution_attempt=t.solution_attempt,
                    success=t.success,
                    error_message=t.error_message,
                    retry_count=t.retry_count,
                    requires_human=t.requires_human,
                    escalation_reason=t.escalation_reason,
                    created_at=t.created_at.isoformat(),
                )
                for t in escalations
            ]
            
            return api_models.ThoughtLogListResponse(
                logs=thought_responses,
                total=len(thought_responses),
            )
            
        except Exception as e:
            logger.error(f"Error fetching escalations: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to fetch escalations: {str(e)}")
    
    @app.get("/v1/thoughts/mission/{mission_id}/consolidated")
    async def get_consolidated_log(
        mission_id: str,
        current_user: User = Depends(get_current_user),
    ) -> dict:
        """
        Get consolidated log for a mission (Protected endpoint)
        
        Args:
            mission_id: Mission identifier
            current_user: Current authenticated user
            
        Returns:
            Consolidated log as text
        """
        try:
            logger.info(f"User '{current_user.username}' fetching consolidated log for mission {mission_id}")
            
            consolidated = thought_log_service.generate_consolidated_log(mission_id)
            
            return {
                "mission_id": mission_id,
                "consolidated_log": consolidated,
            }
            
        except Exception as e:
            logger.error(f"Error generating consolidated log: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to generate log: {str(e)}")
    
    # GitHub Worker Endpoints
    
    from app.application.services.github_worker import GitHubWorker
    github_worker = GitHubWorker()
    
    @app.post("/v1/github/worker", response_model=api_models.GitHubWorkerResponse)
    async def github_worker_operation(
        request: api_models.GitHubWorkerRequest,
        current_user: User = Depends(get_current_user),
    ) -> api_models.GitHubWorkerResponse:
        """
        Execute GitHub worker operations (Protected endpoint)
        
        Args:
            request: GitHub worker request
            current_user: Current authenticated user
            
        Returns:
            Operation result
        """
        try:
            logger.info(f"User '{current_user.username}' executing GitHub operation: {request.operation}")
            
            if request.operation == "create_branch":
                if not request.branch_name:
                    raise HTTPException(status_code=400, detail="branch_name is required")
                
                result = github_worker.create_feature_branch(request.branch_name)
                
            elif request.operation == "submit_pr":
                if not request.pr_title:
                    raise HTTPException(status_code=400, detail="pr_title is required")
                
                result = github_worker.submit_pull_request(
                    title=request.pr_title,
                    body=request.pr_body or "",
                )
                
            elif request.operation == "fetch_ci_status":
                result = github_worker.fetch_ci_status(run_id=request.run_id)
                
            else:
                raise HTTPException(status_code=400, detail=f"Unknown operation: {request.operation}")
            
            return api_models.GitHubWorkerResponse(
                success=result.get("success", False),
                message=result.get("message", ""),
                data=result,
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error executing GitHub operation: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"GitHub operation failed: {str(e)}")
    
    @app.post("/v1/github/ci-heal/{run_id}")
    async def auto_heal_ci_failure(
        run_id: int,
        mission_id: str,
        current_user: User = Depends(get_current_user),
    ) -> dict:
        """
        Automatically attempt to heal a CI failure (Protected endpoint)
        
        Args:
            run_id: Failed workflow run ID
            mission_id: Mission identifier for tracking
            current_user: Current authenticated user
            
        Returns:
            Healing attempt result
        """
        try:
            logger.info(f"User '{current_user.username}' initiating auto-heal for CI run {run_id}")
            
            result = github_worker.auto_heal_ci_failure(
                run_id=run_id,
                mission_id=mission_id,
                thought_log_service=thought_log_service,
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in auto-heal: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Auto-heal failed: {str(e)}")
    
    @app.post("/v1/jarvis/dispatch", response_model=JarvisDispatchResponse)
    async def jarvis_dispatch(
        request: JarvisDispatchRequest,
        current_user: User = Depends(get_current_user),
    ) -> JarvisDispatchResponse:
        """
        Trigger a repository_dispatch event for Jarvis Self-Healing (Protected endpoint)
        
        This endpoint allows Jarvis to trigger GitHub Actions workflows for code creation
        or fixes. The workflow will use GitHub Copilot to apply changes and run tests.
        
        Args:
            request: Jarvis dispatch request with intent and instruction
            current_user: Current authenticated user
            
        Returns:
            Dispatch result with workflow URL
        """
        try:
            logger.info(
                f"User '{current_user.username}' triggering Jarvis dispatch: "
                f"intent='{request.intent}', instruction='{request.instruction[:100]}...'"
            )
            
            # Prepare client payload
            client_payload = {
                "intent": request.intent,
                "instruction": request.instruction,
                "context": request.context or "",
                "triggered_by": current_user.username,
            }
            
            # Trigger repository_dispatch
            result = github_worker.trigger_repository_dispatch(
                event_type="jarvis_order",
                client_payload=client_payload,
            )
            
            if result.get("success"):
                return JarvisDispatchResponse(
                    success=True,
                    message=result.get("message", "Dispatch triggered successfully"),
                    workflow_url=result.get("workflow_url"),
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=result.get("message", "Failed to trigger dispatch")
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error triggering Jarvis dispatch: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Dispatch failed: {str(e)}")

    return app
