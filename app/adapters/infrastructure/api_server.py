# -*- coding: utf-8 -*-
"""FastAPI Server for Headless Control Interface"""

import logging
from datetime import datetime
import platform
from pathlib import Path
from typing import Any, Dict

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

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

# List of tables that should have RLS enabled for security
# Update this list when adding new tables to the database
RLS_PROTECTED_TABLES = [
    'jarvis_capabilities',
    'evolution_rewards',
]

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
    
    # Mount static files for PWA support (manifest, service worker, icons)
    static_path = Path(__file__).parent.parent.parent.parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
        logger.info(f"Static files mounted from: {static_path}")
    else:
        logger.warning(f"Static directory not found at: {static_path}")
    
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
    
    <!-- Security Meta Tags -->
    <meta name="referrer" content="no-referrer">
    <meta http-equiv="X-Content-Type-Options" content="nosniff">
    <meta http-equiv="X-Frame-Options" content="DENY">
    <meta name="robots" content="noindex, nofollow">
    
    <!-- PWA Manifest -->
    <link rel="manifest" href="/static/manifest.json">
    
    <!-- iOS PWA Support -->
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="J.A.R.V.I.S. Strategic HUD">
    <link rel="apple-touch-icon" href="/static/icon-192.png">
    
    <!-- Theme Color -->
    <meta name="theme-color" content="#00d4ff">
    
    <!-- Leaflet CSS for OpenStreetMap -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
          integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
          crossorigin=""/>
    
    <title>J.A.R.V.I.S. Strategic HUD</title>
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
        
        .form-group {
            position: relative;
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
        
        .password-toggle {
            position: absolute;
            right: 12px;
            top: 38px;
            background: transparent;
            border: none;
            color: #00d4ff;
            cursor: pointer;
            font-size: 1.2em;
            padding: 0;
            transition: all 0.3s;
        }
        
        .password-toggle:hover {
            color: #00ff88;
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
            background: rgba(0, 0, 0, 0.6);
            border: 2px solid #00d4ff;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 0 30px rgba(0, 212, 255, 0.2);
            min-height: 150px;
            max-height: 300px;
            overflow-y: auto;
        }
        
        .message {
            margin: 10px 0;
            padding: 12px;
            border-left: 3px solid #00d4ff;
            background: rgba(0, 212, 255, 0.05);
            animation: fadeIn 0.3s ease-in;
            font-size: 1.1em;
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
            font-size: 0.9em;
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
            font-size: 1.1em;
            outline: none;
            transition: all 0.3s;
            resize: none;
            min-height: 60px;
            line-height: 1.5;
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
        
        #voiceButton.muted {
            background: rgba(128, 128, 128, 0.3);
            border-color: #808080;
            color: #808080;
        }
        
        #voiceButton.listening {
            background: rgba(0, 212, 255, 0.2);
            border-color: #00d4ff;
            animation: pulse-blue 2s ease-in-out infinite;
        }
        
        #voiceButton.transcribing {
            background: rgba(255, 0, 0, 0.3);
            border-color: #ff0000;
            animation: pulse 1s ease-in-out infinite;
        }
        
        /* Legacy support */
        #voiceButton.recording {
            background: rgba(255, 0, 0, 0.3);
            border-color: #ff0000;
            animation: pulse 1s ease-in-out infinite;
        }
        
        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 15px rgba(255, 0, 0, 0.5); }
            50% { box-shadow: 0 0 30px rgba(255, 0, 0, 0.8); }
        }
        
        @keyframes pulse-blue {
            0%, 100% { box-shadow: 0 0 15px rgba(0, 212, 255, 0.5); }
            50% { box-shadow: 0 0 30px rgba(0, 212, 255, 0.8); }
        }
        
        /* Input box waveform visual feedback */
        #commandInput.voice-active {
            border-color: #00ff88;
            box-shadow: 0 0 20px rgba(0, 255, 136, 0.5);
            animation: waveform 0.5s ease-in-out infinite;
        }
        
        @keyframes waveform {
            0%, 100% { 
                box-shadow: 0 0 20px rgba(0, 255, 136, 0.5);
            }
            50% { 
                box-shadow: 0 0 30px rgba(0, 255, 136, 0.8), 0 0 40px rgba(0, 255, 136, 0.4);
            }
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
        
        .reactor {
            display: inline-block;
            width: 40px;
            height: 40px;
            border: 4px solid rgba(0, 212, 255, 0.3);
            border-radius: 50%;
            position: relative;
            animation: reactor-pulse 1.5s ease-in-out infinite;
        }
        
        .reactor::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 20px;
            height: 20px;
            background: #00d4ff;
            border-radius: 50%;
            box-shadow: 0 0 20px #00d4ff, 0 0 40px #00d4ff;
            animation: reactor-core 1.5s ease-in-out infinite;
        }
        
        .reactor::after {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 60px;
            height: 60px;
            border: 2px solid rgba(0, 212, 255, 0.2);
            border-radius: 50%;
            animation: reactor-ring 1.5s ease-in-out infinite;
        }
        
        @keyframes reactor-pulse {
            0%, 100% {
                border-color: rgba(0, 212, 255, 0.3);
                box-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
            }
            50% {
                border-color: rgba(0, 212, 255, 0.8);
                box-shadow: 0 0 30px rgba(0, 212, 255, 0.6), 0 0 50px rgba(0, 212, 255, 0.4);
            }
        }
        
        @keyframes reactor-core {
            0%, 100% {
                opacity: 0.7;
                box-shadow: 0 0 20px #00d4ff;
            }
            50% {
                opacity: 1;
                box-shadow: 0 0 40px #00d4ff, 0 0 60px #00d4ff, 0 0 80px #00d4ff;
            }
        }
        
        @keyframes reactor-ring {
            0%, 100% {
                opacity: 0.3;
                transform: translate(-50%, -50%) scale(1);
            }
            50% {
                opacity: 0.6;
                transform: translate(-50%, -50%) scale(1.1);
            }
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
        
        /* Mobile Edge Node Telemetry Panel */
        .telemetry-panel {
            display: none; /* Hidden per user request - info still tracked in background */
        }
        
        .telemetry-item {
            padding: 10px;
            background: rgba(0, 212, 255, 0.05);
            border-left: 3px solid #00d4ff;
            border-radius: 5px;
        }
        
        .telemetry-label {
            font-size: 0.8em;
            color: #00d4ff;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 5px;
        }
        
        .telemetry-value {
            font-size: 1.2em;
            color: #00ff88;
            font-weight: bold;
        }
        
        .battery-low {
            border-left-color: #ff0000;
            background: rgba(255, 0, 0, 0.1);
        }
        
        .battery-low .telemetry-value {
            color: #ff0000;
        }
        
        /* Spatial Orientation Module */
        .spatial-orientation-panel {
            background: rgba(0, 0, 0, 0.6);
            border: 2px solid #00ff88;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            display: none; /* Hidden by default until location is available */
        }
        
        .spatial-orientation-panel.visible {
            display: block;
        }
        
        .spatial-orientation-panel h3 {
            color: #00ff88;
            margin-bottom: 15px;
            text-align: center;
            text-shadow: 0 0 10px #00ff88;
            font-size: 1.2em;
        }
        
        .location-name {
            text-align: center;
            padding: 10px;
            background: rgba(0, 255, 136, 0.05);
            border-left: 3px solid #00ff88;
            border-radius: 5px;
            margin-bottom: 15px;
            color: #00d4ff;
            font-size: 0.95em;
        }
        
        .location-name .primary {
            font-weight: bold;
            color: #00ff88;
            font-size: 1.1em;
            margin-bottom: 5px;
        }
        
        .location-name .secondary {
            font-size: 0.9em;
            color: #00d4ff;
            opacity: 0.8;
        }
        
        .map-container {
            position: relative;
            width: 100%;
            height: 300px;
            border-radius: 8px;
            overflow: hidden;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 2px solid #00ff88;
        }
        
        .map-container:hover {
            box-shadow: 0 0 20px rgba(0, 255, 136, 0.4);
            border-color: #00d4ff;
        }
        
        #map {
            width: 100%;
            height: 100%;
            z-index: 1;
        }
        
        /* Dark mode for Leaflet map tiles */
        .leaflet-tile {
            filter: brightness(0.6) invert(1) contrast(3) hue-rotate(200deg) saturate(0.3) brightness(0.7);
        }
        
        .map-overlay {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(0, 0, 0, 0.7);
            padding: 8px;
            text-align: center;
            color: #00ff88;
            font-size: 0.85em;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        
        .map-container:hover .map-overlay {
            opacity: 1;
        }
        
        /* Evolution Panel */
        .evolution-panel {
            background: rgba(0, 0, 0, 0.6);
            border: 2px solid #ff9500;
            border-radius: 10px;
            padding: 12px 15px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        
        .evolution-panel h3 {
            color: #ff9500;
            margin: 0;
            text-shadow: 0 0 10px #ff9500;
            font-size: 1em;
        }
        
        .evolution-status {
            color: #ff9500;
            font-weight: bold;
            font-size: 1.1em;
        }
        
        /* Mobile responsiveness */
        @media (max-width: 768px) {
            .header h1 {
                font-size: 1.8em;
                letter-spacing: 3px;
            }
            
            .user-info {
                position: static;
                margin-top: 10px;
                text-align: center;
            }
            
            .modal-content {
                padding: 30px 20px;
                max-width: 90%;
            }
            
            .container {
                padding: 10px;
            }
            
            .terminal {
                min-height: 120px;
                max-height: 250px;
                padding: 15px;
            }
            
            .message {
                font-size: 1em;
                padding: 10px;
            }
            
            .input-area {
                flex-direction: row;
                flex-wrap: nowrap;
                gap: 5px;
            }
            
            #commandInput {
                font-size: 1em;
                padding: 12px;
                min-height: 50px;
            }
            
            #voiceButton {
                padding: 12px 15px;
                font-size: 1em;
                min-width: 50px;
            }
            
            #sendButton {
                padding: 12px 20px;
                font-size: 0.9em;
            }
            
            .telemetry-panel {
                grid-template-columns: 1fr;
            }
            
            .spatial-orientation-panel {
                padding: 12px;
            }
            
            .spatial-orientation-panel h3 {
                font-size: 1em;
            }
            
            .location-name {
                padding: 8px;
                font-size: 0.9em;
                margin-bottom: 12px;
            }
            
            .map-container {
                max-height: 250px;
            }
        }
        
        @media (max-width: 480px) {
            .header h1 {
                font-size: 1.5em;
                letter-spacing: 2px;
            }
            
            .header {
                padding: 15px 10px;
            }
            
            .modal-content h2 {
                font-size: 1.3em;
            }
            
            .form-group input {
                font-size: 0.95em;
            }
            
            .message {
                padding: 10px;
                font-size: 1em;
            }
            
            #commandInput {
                font-size: 1em;
                min-height: 50px;
            }
            
            /* Spatial orientation optimizations for portrait mobile */
            .spatial-orientation-panel h3 {
                font-size: 0.95em;
                margin-bottom: 10px;
            }
            
            .location-name {
                font-size: 0.85em;
                margin-bottom: 10px;
            }
            
            .location-name .primary {
                font-size: 1em;
                margin-bottom: 3px;
            }
            
            .location-name .secondary {
                font-size: 0.85em;
            }
            
            .map-container {
                max-height: 200px;
                border-width: 1px;
            }
            
            .map-overlay {
                font-size: 0.75em;
                padding: 6px;
            }
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
                    <input type="text" id="username" name="username" required autocomplete="off">
                </div>
                <div class="form-group">
                    <label for="password">PASSWORD</label>
                    <input type="password" id="password" name="password" required autocomplete="off">
                    <button type="button" class="password-toggle" id="passwordToggle" title="Show/Hide Password">👁️</button>
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
            <!-- Mobile Edge Node Telemetry Panel -->
            <div class="telemetry-panel" id="telemetryPanel">
                <div class="telemetry-item" id="batteryTelemetry">
                    <div class="telemetry-label">Battery</div>
                    <div class="telemetry-value" id="batteryValue">-- %</div>
                </div>
                <div class="telemetry-item">
                    <div class="telemetry-label">Location</div>
                    <div class="telemetry-value" id="locationValue">Detecting...</div>
                </div>
                <div class="telemetry-item">
                    <div class="telemetry-label">Device Type</div>
                    <div class="telemetry-value" id="deviceType">Desktop</div>
                </div>
                <div class="telemetry-item">
                    <div class="telemetry-label">Connection</div>
                    <div class="telemetry-value" id="connectionStatus">Online</div>
                </div>
            </div>
            
            <!-- Spatial Orientation Module -->
            <div class="spatial-orientation-panel" id="spatialOrientationPanel">
                <h3>📍 Orientação Espacial</h3>
                <div class="location-name" id="locationName">
                    <div class="primary">Carregando localização...</div>
                    <div class="secondary"></div>
                </div>
                <div class="map-container" id="mapContainer" title="Clique para abrir no Google Maps">
                    <div id="map"></div>
                    <div class="map-overlay">🗺️ Clique para visualizar no Google Maps</div>
                </div>
            </div>
            
            <!-- Real-Time Evolution Panel -->
            <div class="evolution-panel">
                <h3>⚙️ Progresso:</h3>
                <div class="evolution-status" id="evolutionStatus">0%</div>
            </div>
            
            <div class="terminal" id="terminal">
                <div class="message system">
                    <div class="message-label">System</div>
                    <div>J.A.R.V.I.S. Command Interface initialized. Ready for input.</div>
                </div>
            </div>
            
            <div class="loading" id="loading">
                <div class="reactor"></div>
                <div style="margin-top: 10px;">Processing...</div>
            </div>
            
            <div class="input-area">
                <button id="voiceButton" title="Voice Input">🎤</button>
                <textarea 
                    id="commandInput" 
                    placeholder="Enter command or use voice..."
                    autocomplete="off"
                    rows="2"
                ></textarea>
                <button id="sendButton">Enviar</button>
            </div>
        </div>
    </div>
    
    <!-- Leaflet JavaScript for OpenStreetMap - loaded before inline scripts -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
            integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
            crossorigin=""></script>
    
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
        const passwordToggle = document.getElementById('passwordToggle');
        const passwordInput = document.getElementById('password');
        
        // Voice recognition - V.A.S. (Voice Activated System)
        let recognition = null;
        let isRecording = false;
        let vasState = 'muted'; // 'muted', 'listening' (wake word detection), 'transcribing'
        let silenceTimer = null;
        const SILENCE_TIMEOUT = 3000; // 3 seconds
        // Wake word detection works with Portuguese pronunciation since lang='pt-BR'
        // Both app name (jarvis) and user-configured wake word (e.g., xerife) are supported
        const WAKE_WORDS = ['jarvis']; // Will be updated with configured wake_word from /v1/status
        let lastSpeechTime = Date.now();
        
        // Voice synthesis
        function speak(text) {
            if ('speechSynthesis' in window) {
                // Cancel any ongoing speech
                window.speechSynthesis.cancel();
                
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'pt-BR'; // Portuguese Brazilian
                utterance.rate = 1.0;
                utterance.pitch = 1.0;
                utterance.volume = 1.0;
                
                window.speechSynthesis.speak(utterance);
            }
        }
        
        // Generate time-based greeting
        function getGreeting() {
            const hour = new Date().getHours();
            let timeGreeting;
            
            if (hour >= 5 && hour < 12) {
                timeGreeting = 'Bom dia';
            } else if (hour >= 12 && hour < 18) {
                timeGreeting = 'Boa tarde';
            } else {
                timeGreeting = 'Boa noite';
            }
            
            const welcomeMessages = [
                'Bem-vindo de volta',
                'É bom ter você de volta',
                'Prazer em vê-lo novamente',
                'Sistemas online e prontos'
            ];
            
            const randomWelcome = welcomeMessages[Math.floor(Math.random() * welcomeMessages.length)];
            
            return `${timeGreeting}. ${randomWelcome}.`;
        }
        
        // Initialize Web Speech API for V.A.S.
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechRecognition();
            recognition.continuous = true; // Continuous mode for wake word detection
            recognition.interimResults = true; // Get interim results for real-time transcription
            recognition.lang = 'pt-BR'; // Portuguese Brazilian
            
            recognition.onresult = (event) => {
                const results = event.results;
                const lastResult = results[results.length - 1];
                const transcript = lastResult[0].transcript.trim().toLowerCase();
                
                lastSpeechTime = Date.now();
                
                // Reset silence timer when speech is detected
                if (silenceTimer) {
                    clearTimeout(silenceTimer);
                }
                
                if (vasState === 'listening') {
                    // Wake word detection mode - check for any wake word
                    const detectedWakeWord = WAKE_WORDS.find(word => transcript.includes(word));
                    if (detectedWakeWord) {
                        // Wake word detected! Switch to transcribing mode
                        vasState = 'transcribing';
                        updateVoiceButtonState();
                        commandInput.focus();
                        commandInput.classList.add('voice-active');
                        addMessage(`Wake word "${detectedWakeWord}" detected. Transcribing...`, 'system');
                        // Clear the wake word from input
                        commandInput.value = '';
                    }
                } else if (vasState === 'transcribing') {
                    // Transcription mode - write to input box
                    if (lastResult.isFinal) {
                        // Final result - append to input
                        const currentValue = commandInput.value;
                        const newText = lastResult[0].transcript.trim();
                        commandInput.value = currentValue ? currentValue + ' ' + newText : newText;
                    } else {
                        // Interim result - show in real-time but don't commit yet
                        // For better UX, we'll just use final results
                    }
                    
                    // Start silence detection
                    silenceTimer = setTimeout(() => {
                        handleSilence();
                    }, SILENCE_TIMEOUT);
                    
                    // Visual feedback during speech
                    commandInput.classList.add('voice-active');
                }
            };
            
            recognition.onerror = (event) => {
                console.error('Speech recognition error:', event.error);
                
                // Don't show error message for 'no-speech' - it's expected during listening
                if (event.error !== 'no-speech') {
                    addMessage(`Voice error: ${event.error}`, 'system');
                }
                
                // Reset state on certain errors
                if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                    vasState = 'muted';
                    isRecording = false;
                    updateVoiceButtonState();
                    addMessage('Microphone access denied. Please allow microphone permissions.', 'system');
                }
            };
            
            recognition.onend = () => {
                // Only stop if we're in muted state, otherwise restart for continuous listening
                if (vasState === 'listening' && isRecording) {
                    // Restart for continuous wake word detection
                    try {
                        recognition.start();
                    } catch (e) {
                        // Ignore if already started; log other errors
                        if (e.name !== 'InvalidStateError') {
                            console.error('Recognition restart error:', e);
                        }
                    }
                } else if (vasState === 'transcribing' && isRecording) {
                    // Keep transcribing until manually stopped or silence detected
                    try {
                        recognition.start();
                    } catch (e) {
                        // Ignore if already started; log other errors
                        if (e.name !== 'InvalidStateError') {
                            console.error('Recognition restart error:', e);
                        }
                    }
                } else {
                    isRecording = false;
                    updateVoiceButtonState();
                }
            };
            
            recognition.onstart = () => {
                isRecording = true;
            };
        } else {
            // Browser doesn't support Speech API - show fallback message
            addMessage('Comando de voz indisponível neste ambiente', 'system');
            voiceButton.style.display = 'none';
        }
        
        // Handle silence detection
        function handleSilence() {
            if (vasState === 'transcribing') {
                // Silence detected - return to wake word listening mode
                vasState = 'listening';
                updateVoiceButtonState();
                commandInput.classList.remove('voice-active');
                addMessage('Silence detected. Returning to wake word mode...', 'system');
            }
        }
        
        // Update voice button visual state
        function updateVoiceButtonState() {
            // Remove all state classes
            voiceButton.classList.remove('muted', 'listening', 'transcribing', 'recording');
            
            // Add current state class
            voiceButton.classList.add(vasState);
            
            // Update button icon/text based on state
            if (vasState === 'muted') {
                voiceButton.innerHTML = '🔇';
                voiceButton.title = 'Microphone Off - Click to enable wake word detection';
            } else if (vasState === 'listening') {
                voiceButton.innerHTML = '🎤';
                const wakeWordsDisplay = WAKE_WORDS.join('" or "');
                voiceButton.title = `Listening for wake word "${wakeWordsDisplay}" - Click to mute`;
            } else if (vasState === 'transcribing') {
                voiceButton.innerHTML = '🔴';
                voiceButton.title = 'Transcribing - Click to stop';
            }
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
        async function showMainInterface(username) {
            userDisplay.textContent = `User: ${username}`;
            loginModal.classList.remove('active');
            mainInterface.classList.remove('hidden');
            commandInput.focus();
            
            // Fetch wake word from status endpoint and add it to WAKE_WORDS (non-blocking)
            fetchWakeWord();
            
            // Greet the user when HUD opens
            const greeting = getGreeting();
            addMessage(greeting, 'jarvis');
            speak(greeting);
        }
        
        // Fetch configured wake word from backend
        async function fetchWakeWord() {
            try {
                const token = localStorage.getItem(AUTH_TOKEN_KEY);
                const response = await fetch('/v1/status', {
                    method: 'GET',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    if (data.wake_word && !WAKE_WORDS.includes(data.wake_word)) {
                        WAKE_WORDS.push(data.wake_word);
                        console.log(`Wake words configured: ${WAKE_WORDS.join(', ')}`);
                    }
                }
            } catch (error) {
                console.error('Error fetching wake word:', error);
                // Continue with default wake words if fetch fails
            }
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
        
        // Password toggle handler
        if (passwordToggle) {
            passwordToggle.addEventListener('click', () => {
                if (passwordInput.type === 'password') {
                    passwordInput.type = 'text';
                    passwordToggle.textContent = '🙈';
                } else {
                    passwordInput.type = 'password';
                    passwordToggle.textContent = '👁️';
                }
            });
        }
        
        // Logout handler
        logoutBtn.addEventListener('click', logout);
        
        // Voice button handler for V.A.S.
        if (voiceButton) {
            voiceButton.addEventListener('click', () => {
                if (!recognition) {
                    addMessage('Voice recognition not supported in this browser', 'system');
                    return;
                }
                
                if (vasState === 'muted') {
                    // Start wake word listening mode
                    vasState = 'listening';
                    try {
                        recognition.start();
                        updateVoiceButtonState();
                        addMessage('Wake word detection active. Say "Jarvis" to start transcribing.', 'system');
                    } catch (e) {
                        console.error('Failed to start recognition:', e);
                        vasState = 'muted';
                        updateVoiceButtonState();
                    }
                } else if (vasState === 'listening') {
                    // Stop and mute
                    vasState = 'muted';
                    try {
                        recognition.stop();
                    } catch (e) {
                        // Ignore if already stopped; log other errors
                        if (e.name !== 'InvalidStateError') {
                            console.error('Recognition stop error:', e);
                        }
                    }
                    isRecording = false;
                    updateVoiceButtonState();
                    addMessage('Voice detection disabled.', 'system');
                } else if (vasState === 'transcribing') {
                    // Stop transcribing and return to listening mode
                    vasState = 'listening';
                    commandInput.classList.remove('voice-active');
                    if (silenceTimer) {
                        clearTimeout(silenceTimer);
                        silenceTimer = null;
                    }
                    updateVoiceButtonState();
                    addMessage('Transcription stopped. Back to wake word mode.', 'system');
                }
            });
            
            // Initialize button state
            updateVoiceButtonState();
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
            
            // Keep only the last 2 messages for better mobile readability
            const messages = terminal.querySelectorAll('.message');
            if (messages.length > 2) {
                // Remove oldest messages, keeping only last 2 regardless of sender
                for (let i = 0; i < messages.length - 2; i++) {
                    messages[i].remove();
                }
            }
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
                const response = await fetch('/v1/message', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        text: command
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
                
                // Extract and display the response field
                if (data.response) {
                    addMessage(data.response, 'system');
                    // Speak the response aloud
                    speak(data.response);
                } else if (data.error) {
                    addMessage(`Error: ${data.error}`, 'system');
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
        
        // Send on Enter key (Shift+Enter for new line in textarea)
        commandInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault(); // Prevent new line
                sendCommand();
            }
            // Shift+Enter will create a new line (default behavior)
        });
        
        // Initialize app
        checkAuth();
        
        // ============================================
        // Mobile Edge Node Telemetry System
        // ============================================
        
        // Configuration constants
        const BATTERY_LOW_THRESHOLD = 15; // Percentage - triggers power-saving mode
        const TELEMETRY_INTERVAL_MS = 30000; // 30 seconds
        const GPS_CACHE_MAX_AGE_MS = 300000; // 5 minutes
        const SIGNIFICANT_DISPLACEMENT_METERS = 100; // Performance requirement: update map only if position changes > 100m
        
        let batteryLevel = 100;
        let batteryCharging = false;
        let currentLocation = null;
        let lastMapLocation = null; // Track last location where map was updated
        let deviceType = detectDeviceType();
        let telemetryInterval = null;
        let leafletMap = null; // Leaflet map instance
        let mapMarker = null; // Map marker instance
        
        // Detect device type using user agent
        // Maps various mobile/tablet user agents to device categories
        function detectDeviceType() {
            const ua = navigator.userAgent.toLowerCase();
            // Tablet detection: iPads, Android tablets, Surface tablets, etc.
            if (/(tablet|ipad|playbook|silk)|(android(?!.*mobi))/i.test(ua)) {
                return 'Tablet';
            }
            // Mobile detection: smartphones, feature phones
            if (/mobile|iphone|ipod|android|blackberry|opera mini|opera mobi|skyfire|maemo|windows phone|palm|iemobile|symbian|symbianos|fennec/i.test(ua)) {
                return 'Mobile';
            }
            return 'Desktop';
        }
        
        // Update device type display
        document.getElementById('deviceType').textContent = deviceType;
        
        // Initialize Battery API
        async function initBatteryMonitoring() {
            if ('getBattery' in navigator) {
                try {
                    const battery = await navigator.getBattery();
                    
                    // Update battery level
                    function updateBatteryStatus() {
                        batteryLevel = Math.round(battery.level * 100);
                        batteryCharging = battery.charging;
                        
                        const batteryValue = document.getElementById('batteryValue');
                        const batteryTelemetry = document.getElementById('batteryTelemetry');
                        
                        batteryValue.textContent = `${batteryLevel}% ${batteryCharging ? '⚡' : ''}`;
                        
                        // Low battery warning (uses BATTERY_LOW_THRESHOLD constant)
                        if (batteryLevel < BATTERY_LOW_THRESHOLD && !batteryCharging) {
                            batteryTelemetry.classList.add('battery-low');
                            checkBatteryEmergency();
                        } else {
                            batteryTelemetry.classList.remove('battery-low');
                        }
                    }
                    
                    // Initial update
                    updateBatteryStatus();
                    
                    // Listen for changes
                    battery.addEventListener('levelchange', updateBatteryStatus);
                    battery.addEventListener('chargingchange', updateBatteryStatus);
                    
                } catch (error) {
                    console.error('Battery API error:', error);
                    document.getElementById('batteryValue').textContent = 'N/A';
                }
            } else {
                document.getElementById('batteryValue').textContent = 'N/A';
            }
        }
        
        // Calculate distance between two coordinates using Haversine formula
        function calculateDistance(lat1, lon1, lat2, lon2) {
            const R = 6371e3; // Earth's radius in meters
            const φ1 = lat1 * Math.PI / 180;
            const φ2 = lat2 * Math.PI / 180;
            const Δφ = (lat2 - lat1) * Math.PI / 180;
            const Δλ = (lon2 - lon1) * Math.PI / 180;
            
            // Cache sine calculations for efficiency
            const sinHalfDeltaPhi = Math.sin(Δφ/2);
            const sinHalfDeltaLambda = Math.sin(Δλ/2);
            
            const a = sinHalfDeltaPhi * sinHalfDeltaPhi +
                      Math.cos(φ1) * Math.cos(φ2) *
                      sinHalfDeltaLambda * sinHalfDeltaLambda;
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            
            return R * c; // Distance in meters
        }
        
        // Update the spatial orientation module with map and geocoding
        async function updateSpatialOrientation(latitude, longitude) {
            const panel = document.getElementById('spatialOrientationPanel');
            const mapContainer = document.getElementById('mapContainer');
            const locationName = document.getElementById('locationName');
            
            // Check if we should update the map (significant displacement or first time)
            if (lastMapLocation) {
                const distance = calculateDistance(
                    lastMapLocation.latitude,
                    lastMapLocation.longitude,
                    latitude,
                    longitude
                );
                
                // Only update if displacement is significant
                if (distance < SIGNIFICANT_DISPLACEMENT_METERS) {
                    console.log(`Displacement: ${distance.toFixed(2)}m - Skipping map update`);
                    return;
                }
                
                console.log(`Significant displacement: ${distance.toFixed(2)}m - Updating map`);
            }
            
            // Update last map location
            lastMapLocation = { latitude, longitude };
            
            // Initialize Leaflet map if not already initialized
            if (!leafletMap) {
                leafletMap = L.map('map', {
                    zoomControl: true,
                    attributionControl: true,
                    dragging: false,
                    scrollWheelZoom: false,
                    doubleClickZoom: false,
                    boxZoom: false,
                    keyboard: false,
                    tap: false
                }).setView([latitude, longitude], 16);
                
                // Add OpenStreetMap tiles with dark mode styling
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                    maxZoom: 19,
                }).addTo(leafletMap);
                
                // Create a custom icon for the marker
                const customIcon = L.divIcon({
                    className: 'custom-marker',
                    html: '<div style="background-color: #00ff88; width: 20px; height: 20px; border-radius: 50%; border: 3px solid #00d4ff; box-shadow: 0 0 10px rgba(0, 255, 136, 0.6);"></div>',
                    iconSize: [20, 20],
                    iconAnchor: [10, 10]
                });
                
                // Add marker
                mapMarker = L.marker([latitude, longitude], { icon: customIcon }).addTo(leafletMap);
            } else {
                // Update map view and marker position
                leafletMap.setView([latitude, longitude], 16);
                mapMarker.setLatLng([latitude, longitude]);
            }
            
            // Make map clickable - redirect to Google Maps
            mapContainer.onclick = () => {
                const googleMapsUrl = `https://www.google.com/maps?q=${latitude},${longitude}`;
                window.open(googleMapsUrl, '_blank');
            };
            
            // Fetch location name using Nominatim (OSM) Reverse Geocoding
            try {
                const nominatimUrl = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&zoom=18&addressdetails=1`;
                const response = await fetch(nominatimUrl, {
                    headers: {
                        'User-Agent': 'JARVIS-HUD/1.0 (https://github.com/TheDrack/Jarvis_Xerife)'
                    }
                });
                const data = await response.json();
                
                if (data && data.address) {
                    const address = data.address;
                    
                    // Extract neighborhood, suburb, or locality
                    const neighborhood = address.neighbourhood || address.suburb || address.quarter || '';
                    const locality = address.city || address.town || address.village || address.municipality || '';
                    const establishment = address.amenity || address.building || '';
                    
                    // Display location name with clear logic
                    const primaryLocation = establishment || neighborhood || locality || 'Localização atual';
                    
                    // Determine secondary location
                    let secondaryLocation = '';
                    if (establishment && neighborhood) {
                        secondaryLocation = neighborhood;
                    } else if (establishment && locality) {
                        secondaryLocation = locality;
                    } else if (neighborhood && locality) {
                        secondaryLocation = locality;
                    }
                    
                    locationName.innerHTML = `
                        <div class="primary">${primaryLocation}</div>
                        ${secondaryLocation ? `<div class="secondary">${secondaryLocation}</div>` : ''}
                    `;
                } else {
                    locationName.innerHTML = `
                        <div class="primary">Localização: ${latitude.toFixed(4)}, ${longitude.toFixed(4)}</div>
                    `;
                }
            } catch (error) {
                console.error('Nominatim geocoding error:', error);
                locationName.innerHTML = `
                    <div class="primary">Localização: ${latitude.toFixed(4)}, ${longitude.toFixed(4)}</div>
                `;
            }
            
            // Show the panel
            panel.classList.add('visible');
        }
        
        // Initialize Geolocation with spatial orientation module
        function initGeolocation() {
            if ('geolocation' in navigator) {
                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        currentLocation = {
                            latitude: position.coords.latitude,
                            longitude: position.coords.longitude,
                            accuracy: position.coords.accuracy
                        };
                        
                        const lat = position.coords.latitude.toFixed(4);
                        const lon = position.coords.longitude.toFixed(4);
                        document.getElementById('locationValue').textContent = `${lat}, ${lon}`;
                        
                        // Update spatial orientation module
                        updateSpatialOrientation(position.coords.latitude, position.coords.longitude);
                    },
                    (error) => {
                        console.error('Geolocation error:', error);
                        document.getElementById('locationValue').textContent = 'Denied';
                        // Keep spatial orientation panel hidden if location is denied
                    },
                    {
                        enableHighAccuracy: false, // Low accuracy to save battery on all devices
                        timeout: 10000,
                        maximumAge: GPS_CACHE_MAX_AGE_MS
                    }
                );
                
                // Watch for location changes and update spatial orientation
                navigator.geolocation.watchPosition(
                    (position) => {
                        currentLocation = {
                            latitude: position.coords.latitude,
                            longitude: position.coords.longitude,
                            accuracy: position.coords.accuracy
                        };
                        
                        const lat = position.coords.latitude.toFixed(4);
                        const lon = position.coords.longitude.toFixed(4);
                        document.getElementById('locationValue').textContent = `${lat}, ${lon}`;
                        
                        // Update spatial orientation (will only update map if displacement > 50m)
                        updateSpatialOrientation(position.coords.latitude, position.coords.longitude);
                    },
                    (error) => {
                        console.error('Geolocation watch error:', error);
                    },
                    {
                        enableHighAccuracy: false,
                        timeout: 10000,
                        maximumAge: GPS_CACHE_MAX_AGE_MS
                    }
                );
            } else {
                document.getElementById('locationValue').textContent = 'N/A';
            }
        }
        
        // Send telemetry to JARVIS
        async function sendTelemetry() {
            const token = localStorage.getItem(AUTH_TOKEN_KEY);
            if (!token) return;
            
            const telemetryData = {
                device_type: deviceType,
                battery: {
                    level: batteryLevel,
                    charging: batteryCharging
                },
                location: currentLocation,
                timestamp: new Date().toISOString()
            };
            
            try {
                // Send via API (you can also use WebSocket for real-time updates)
                await fetch('/v1/telemetry', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(telemetryData)
                });
            } catch (error) {
                console.error('Telemetry error:', error);
            }
        }
        
        // Battery Emergency - Suggest power saving
        async function checkBatteryEmergency() {
            if (batteryLevel < BATTERY_LOW_THRESHOLD && !batteryCharging) {
                const message = `⚠️ ALERTA: Bateria baixa (${batteryLevel}%). Sugerindo modo de economia de energia.`;
                addMessage(message, 'system');
                
                // Auto-suggest power saving to JARVIS
                const token = localStorage.getItem(AUTH_TOKEN_KEY);
                if (token) {
                    try {
                        await fetch('/v1/message', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': `Bearer ${token}`
                            },
                            body: JSON.stringify({
                                text: `Bateria crítica (${batteryLevel}%). Ative modo economia.`,
                                priority: 'high',
                                source: 'mobile_telemetry'
                            })
                        });
                    } catch (error) {
                        console.error('Failed to send battery alert:', error);
                    }
                }
            }
        }
        
        // Evolution tracking
        async function updateEvolutionStatus() {
            const token = localStorage.getItem(AUTH_TOKEN_KEY);
            if (!token) return;
            
            try {
                // Fetch roadmap progress from JARVIS
                const response = await fetch('/v1/roadmap/progress', {
                    method: 'GET',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    
                    const evolutionStatus = document.getElementById('evolutionStatus');
                    const pluginCount = document.getElementById('pluginCount');
                    
                    // Display roadmap completion percentage
                    if (data.completion_percentage !== undefined) {
                        evolutionStatus.innerHTML = `
                            <div><strong>${data.completion_percentage.toFixed(1)}%</strong></div>
                            <div style="margin-top: 5px; font-size: 0.85em;">
                                ✅ ${data.completed || 0} | 🔄 ${data.in_progress || 0} | 📋 ${data.planned || 0}
                            </div>
                        `;
                    } else if (data.error) {
                        evolutionStatus.innerHTML = `
                            <div>❌ Erro</div>
                            <div style="margin-top: 5px; font-size: 0.85em;">${data.error}</div>
                        `;
                    }
                    
                    // Update plugin count if available (keeping backward compatibility)
                    if (data.plugin_count !== undefined) {
                        pluginCount.textContent = data.plugin_count;
                    }
                }
            } catch (error) {
                console.error('Evolution status error:', error);
            }
        }
        
        // Start telemetry monitoring
        function startTelemetryMonitoring() {
            // Initialize monitors
            initBatteryMonitoring();
            initGeolocation();
            
            // Send telemetry at configured interval (TELEMETRY_INTERVAL_MS)
            telemetryInterval = setInterval(() => {
                sendTelemetry();
                updateEvolutionStatus();
            }, TELEMETRY_INTERVAL_MS);
            
            // Initial evolution status
            updateEvolutionStatus();
        }
        
        // Start telemetry when authenticated
        if (checkAuth()) {
            startTelemetryMonitoring();
        }
        
        // ============================================
        // PWA Service Worker Registration
        // ============================================
        
        // Register service worker for PWA functionality
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/static/sw.js')
                    .then((registration) => {
                        console.log('Service Worker registered successfully:', registration.scope);
                    })
                    .catch((error) => {
                        console.error('Service Worker registration failed:', error);
                    });
            });
        }
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
            
            # Log the response for debugging (helps identify if responses are generated but not shown in HUD)
            logger.info(f"Generated response for user '{current_user.username}': success={response.success}, message_length={len(response.message) if response.message else 0}")

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
            
            # Log the response for debugging (helps identify if responses are generated but not shown in HUD)
            logger.info(f"Generated response for user '{current_user.username}': success={response.success}, message_length={len(response.message) if response.message else 0}")

            return MessageResponse(
                success=response.success,
                response=response.message,
                error=response.error,
            )
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return MessageResponse(
                success=False,
                response="Erro ao processar mensagem. Tente novamente.",
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
        """
        Health check endpoint that validates database connectivity and security settings.
        
        Returns:
            JSON response with health status, database connectivity, and RLS security status
        """
        response = {
            "status": "healthy",
            "version": "1.0.0",
            "database": {
                "connected": False,
                "type": "unknown"
            },
            "security": {
                "rls_enabled": False,
                "tables_checked": [],
                "tables_without_rls": []
            }
        }
        
        try:
            # Check if database URL is configured for SQLite
            if not settings.database_url or settings.database_url.startswith('sqlite://'):
                # SQLite doesn't support RLS
                response["database"]["connected"] = True
                response["database"]["type"] = "sqlite"
                response["security"]["rls_enabled"] = "n/a"
                response["security"]["note"] = "SQLite does not support Row Level Security"
                return response
            
            # For PostgreSQL/Supabase databases, check RLS status
            if "postgresql" in settings.database_url or "postgres" in settings.database_url:
                response["database"]["type"] = "postgresql"
                
                # Try to connect and check RLS status
                from sqlmodel import Session, text
                
                with Session(db_adapter.engine) as session:
                    # Test database connectivity
                    session.exec(text("SELECT 1"))
                    response["database"]["connected"] = True
                    
                    # Check RLS status for all tables in the public schema
                    # Build the IN clause dynamically from RLS_PROTECTED_TABLES
                    table_list = ", ".join(f"'{table}'" for table in RLS_PROTECTED_TABLES)
                    rls_query = text(f"""
                        SELECT 
                            schemaname,
                            tablename,
                            rowsecurity
                        FROM pg_tables 
                        WHERE schemaname = 'public'
                        AND tablename IN ({table_list})
                        ORDER BY tablename
                    """)
                    
                    results = session.exec(rls_query).fetchall()
                    
                    tables_with_rls = []
                    tables_without_rls = []
                    
                    for row in results:
                        table_name = row[1]  # tablename
                        rls_enabled = row[2]  # rowsecurity
                        
                        response["security"]["tables_checked"].append(table_name)
                        
                        if rls_enabled:
                            tables_with_rls.append(table_name)
                        else:
                            tables_without_rls.append(table_name)
                    
                    response["security"]["tables_without_rls"] = tables_without_rls
                    
                    # All tables should have RLS enabled
                    if len(tables_without_rls) == 0 and len(tables_with_rls) > 0:
                        response["security"]["rls_enabled"] = True
                        response["status"] = "healthy"
                    elif len(tables_without_rls) > 0:
                        response["security"]["rls_enabled"] = False
                        response["status"] = "degraded"
                        response["security"]["warning"] = f"Row Level Security is NOT enabled on: {', '.join(tables_without_rls)}"
                    else:
                        # No tables found
                        response["security"]["rls_enabled"] = "unknown"
                        response["security"]["note"] = "No tables found in database"
                        
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            response["status"] = "unhealthy"
            response["database"]["connected"] = False
            response["error"] = str(e)
        
        return response

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
        
        **IMPORTANTE: Use este endpoint para correções/criações de código automáticas.**
        
        Este endpoint envia prompts para GitHub Agents (via repository_dispatch),
        que executam correções/criações de código automaticamente.
        
        NÃO confundir com criação de Issues (que é para rastreamento manual).
        
        This endpoint allows Jarvis to trigger GitHub Actions workflows for code creation
        or fixes. The workflow will use GitHub Copilot to apply changes and run tests.
        
        Args:
            request: Jarvis dispatch request with intent ('create' or 'fix') and instruction
            current_user: Current authenticated user
            
        Returns:
            Dispatch result with workflow URL
            
        Example:
            POST /v1/jarvis/dispatch
            {
                "intent": "fix",
                "instruction": "Fix the TypeError in user_service.py line 42",
                "context": "The error occurs when calling get_user with invalid ID"
            }
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

    # Evolution and Self-Awareness Endpoints
    
    @app.get("/v1/status/evolution", response_model=api_models.EvolutionStatusResponse)
    async def get_evolution_status():
        """
        Get JARVIS evolution status and progress.
        
        Returns the overall evolution progress and chapter-by-chapter breakdown
        of the 102 capabilities defined in JARVIS_OBJECTIVES_MAP.
        
        This endpoint provides visibility into JARVIS self-awareness and
        capability development across 9 chapters.
        
        Returns:
            Evolution status with overall and chapter progress
        """
        try:
            from app.application.services.capability_manager import CapabilityManager
            
            # Initialize capability manager
            capability_manager = CapabilityManager(engine=db_adapter.engine)
            
            # Get evolution progress
            progress = capability_manager.get_evolution_progress()
            
            return api_models.EvolutionStatusResponse(
                overall_progress=progress["overall_progress"],
                total_capabilities=progress["total_capabilities"],
                complete_capabilities=progress["complete_capabilities"],
                partial_capabilities=progress["partial_capabilities"],
                nonexistent_capabilities=progress["nonexistent_capabilities"],
                chapters=[
                    api_models.ChapterProgress(**chapter)
                    for chapter in progress["chapters"]
                ]
            )
            
        except Exception as e:
            logger.error(f"Error getting evolution status: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to get evolution status: {str(e)}")
    
    @app.get("/v1/evolution/next-step", response_model=api_models.NextEvolutionStepResponse)
    async def get_next_evolution_step():
        """
        Get the next capability that JARVIS should implement.
        
        This is the self-evolution trigger. It returns the highest-priority
        capability that has all technical requirements satisfied and is ready
        for implementation.
        
        Returns:
            Next evolution step with capability details and technical blueprint
            
        Raises:
            404: If no capabilities are ready for implementation
        """
        try:
            from app.application.services.capability_manager import CapabilityManager
            
            # Initialize capability manager
            capability_manager = CapabilityManager(engine=db_adapter.engine)
            
            # Get next evolution step
            next_step = capability_manager.get_next_evolution_step()
            
            if next_step is None:
                raise HTTPException(
                    status_code=404,
                    detail="No capabilities ready for implementation. All capabilities either complete or have missing resources."
                )
            
            # Convert blueprint to CapabilityRequirements model
            blueprint_data = next_step["blueprint"]
            blueprint_model = api_models.CapabilityRequirements(**blueprint_data)
            
            return api_models.NextEvolutionStepResponse(
                capability_id=next_step["capability_id"],
                capability_name=next_step["capability_name"],
                chapter=next_step["chapter"],
                current_status=next_step["current_status"],
                blueprint=blueprint_model,
                priority_score=next_step["priority_score"]
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting next evolution step: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to get next evolution step: {str(e)}")
    
    @app.post("/v1/evolution/scan", response_model=Dict[str, Any])
    async def scan_capabilities():
        """
        Scan the repository to detect which capabilities are already implemented.
        
        This endpoint triggers a full scan of the codebase to identify
        existing functionality and update capability statuses accordingly.
        
        Returns:
            Scan results with updated capabilities and status counts
        """
        try:
            from app.application.services.capability_manager import CapabilityManager
            
            # Initialize capability manager
            capability_manager = CapabilityManager(engine=db_adapter.engine)
            
            # Run status scan
            scan_results = capability_manager.status_scan()
            
            return scan_results
            
        except Exception as e:
            logger.error(f"Error scanning capabilities: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to scan capabilities: {str(e)}")
    
    @app.get("/v1/evolution/requirements/{capability_id}", response_model=api_models.CapabilityRequirements)
    async def get_capability_requirements(capability_id: int):
        """
        Get technical requirements for a specific capability.
        
        Returns a technical blueprint describing what libraries, APIs,
        environment variables, and permissions are needed to implement
        the specified capability.
        
        Args:
            capability_id: The ID of the capability (1-102)
            
        Returns:
            Technical blueprint with all requirements
        """
        try:
            from app.application.services.capability_manager import CapabilityManager
            
            # Initialize capability manager
            capability_manager = CapabilityManager(engine=db_adapter.engine)
            
            # Get requirements
            blueprint = capability_manager.check_requirements(capability_id)
            
            if "error" in blueprint:
                raise HTTPException(status_code=404, detail=blueprint["error"])
            
            return api_models.CapabilityRequirements(**blueprint)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting capability requirements: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to get requirements: {str(e)}")
    
    # Local Bridge WebSocket Endpoint for GUI Delegation
    
    @app.websocket("/v1/local-bridge")
    async def local_bridge_websocket(
        websocket: WebSocket, 
        device_id: str = "default",
        device_type: str = "desktop"
    ):
        """
        WebSocket endpoint for connecting local PC or mobile device to JARVIS.
        
        Enables JARVIS (running in the cloud) to delegate GUI tasks (PyAutoGUI)
        or mobile-specific tasks (camera, sensors, vibration) to connected devices.
        
        Query Parameters:
            device_id: Unique identifier for the device
            device_type: Type of device (desktop, mobile, tablet) - default: desktop
            
        Usage:
            Desktop: ws://jarvis-host/v1/local-bridge?device_id=my_pc&device_type=desktop
            Mobile:  ws://jarvis-host/v1/local-bridge?device_id=my_phone&device_type=mobile
        """
        from app.application.services.local_bridge import get_bridge_manager
        
        bridge_manager = get_bridge_manager()
        
        try:
            # Accept connection with device type
            await bridge_manager.connect(websocket, device_id, device_type)
            
            # Handle messages
            while True:
                try:
                    # Receive message from device
                    data = await websocket.receive_json()
                    await bridge_manager.handle_message(device_id, data)
                    
                except WebSocketDisconnect:
                    logger.info(f"Device disconnected: {device_id}")
                    break
                except Exception as e:
                    logger.error(f"Error handling message from {device_id}: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e)
                    })
        
        finally:
            bridge_manager.disconnect(device_id)
    
    @app.get("/v1/local-bridge/devices")
    async def list_connected_devices():
        """
        List all connected local devices.
        
        Returns:
            List of connected device IDs
        """
        from app.application.services.local_bridge import get_bridge_manager
        
        bridge_manager = get_bridge_manager()
        devices = bridge_manager.get_connected_devices()
        
        return {
            "connected_devices": devices,
            "count": len(devices)
        }
    
    @app.post("/v1/local-bridge/send-task")
    async def send_task_to_local_device(device_id: str, task: Dict[str, Any]):
        """
        Send a task to a connected local device.
        
        Args:
            device_id: Target device ID
            task: Task definition with 'action' and 'parameters'
            
        Returns:
            Task result from the local device
        """
        from app.application.services.local_bridge import get_bridge_manager
        
        bridge_manager = get_bridge_manager()
        
        if not bridge_manager.is_device_connected(device_id):
            raise HTTPException(
                status_code=404,
                detail=f"Device {device_id} is not connected"
            )
        
        result = await bridge_manager.send_task(device_id, task)
        return result
    
    # Scavenger Hunt Endpoint for Missing API Keys
    
    @app.get("/v1/scavenger-hunt/api-keys")
    async def get_api_key_guides(api_key_names: str = None):
        """
        Get guides for obtaining API keys.
        
        When JARVIS encounters missing API keys, this endpoint provides
        step-by-step instructions on how to obtain them.
        
        Query Parameters:
            api_key_names: Comma-separated list of API key names (optional)
                          If not provided, returns guides for all known keys
                          
        Returns:
            Dictionary of API key guides
        """
        from app.application.services.scavenger_hunt import ScavengerHunt
        
        if api_key_names:
            # Get specific guides
            keys = [k.strip() for k in api_key_names.split(",")]
            guides = {}
            
            for key in keys:
                guide = ScavengerHunt.find_guide(key)
                if guide:
                    guides[key] = {
                        "service_name": guide.service_name,
                        "key_name": guide.key_name,
                        "steps": guide.steps,
                        "documentation_url": guide.documentation_url,
                        "is_free": guide.is_free,
                        "estimated_time": guide.estimated_time
                    }
            
            return guides
        else:
            # Return all guides
            all_guides = {}
            for key, guide in ScavengerHunt.API_KEY_GUIDES.items():
                all_guides[key] = {
                    "service_name": guide.service_name,
                    "key_name": guide.key_name,
                    "steps": guide.steps,
                    "documentation_url": guide.documentation_url,
                    "is_free": guide.is_free,
                    "estimated_time": guide.estimated_time
                }
            
            return all_guides
    
    @app.post("/v1/scavenger-hunt/missing-resources")
    async def analyze_missing_resources(capability_id: int):
        """
        Analyze missing resources for a capability and provide acquisition guides.
        
        Args:
            capability_id: The capability ID to analyze
            
        Returns:
            Categorized missing resources with acquisition instructions
        """
        from app.application.services.capability_manager import CapabilityManager
        from app.application.services.scavenger_hunt import ScavengerHunt
        
        try:
            # Initialize capability manager
            capability_manager = CapabilityManager(engine=db_adapter.engine)
            
            # Check for missing resources
            alert = capability_manager.resource_request(capability_id)
            
            if alert is None:
                return {
                    "capability_id": capability_id,
                    "has_missing_resources": False,
                    "message": "All resources are available for this capability"
                }
            
            # Categorize and provide guides
            categorized = ScavengerHunt.search_for_missing_resources(
                alert["missing_resources"]
            )
            
            # Generate acquisition report for API keys
            api_key_names = [
                res.get("name") for res in alert["missing_resources"]
                if res.get("type") == "environment_variable"
            ]
            
            report = None
            if api_key_names:
                report = ScavengerHunt.generate_acquisition_report(api_key_names)
            
            return {
                "capability_id": capability_id,
                "capability_name": alert["capability_name"],
                "has_missing_resources": True,
                "missing_resources": alert["missing_resources"],
                "categorized": categorized,
                "acquisition_report": report,
                "alert_level": alert["alert_level"]
            }
            
        except Exception as e:
            logger.error(f"Error analyzing missing resources: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to analyze resources: {str(e)}"
            )
    
    # Mobile Edge Node Telemetry Endpoints
    
    # Configuration constants
    BATTERY_LOW_THRESHOLD = 15  # Percentage - triggers power-saving suggestions
    PLUGINS_DYNAMIC_DIR = "app/plugins/dynamic"  # Directory for dynamically created plugins
    
    @app.post("/v1/telemetry")
    async def receive_telemetry(
        telemetry_data: Dict[str, Any],
        current_user: User = Depends(get_current_user)
    ):
        """
        Receive telemetry data from mobile/desktop clients.
        
        Telemetry includes battery status, GPS location, device type, etc.
        Used for context-aware assistance and urgency detection (Meta 37, 38).
        
        Args:
            telemetry_data: Telemetry information from client
            current_user: Current authenticated user
            
        Returns:
            Acknowledgment and any suggestions
        """
        logger.info(f"Telemetry received from {current_user.username}: {telemetry_data}")
        
        response = {
            "status": "received",
            "timestamp": datetime.now().isoformat()
        }
        
        # Check for low battery and suggest power saving (Meta 91)
        if telemetry_data.get("battery"):
            battery_level = telemetry_data["battery"].get("level", 100)
            battery_charging = telemetry_data["battery"].get("charging", False)
            
            if battery_level < BATTERY_LOW_THRESHOLD and not battery_charging:
                response["suggestions"] = [
                    "Bateria crítica detectada. Sugerindo desativar funções pesadas da HUD.",
                    "Reduzir frequência de telemetria para economizar bateria.",
                    "Considerar modo de economia de energia."
                ]
                response["priority"] = "high"
                
                logger.warning(f"Low battery detected for {current_user.username}: {battery_level}%")
        
        # Store telemetry for context awareness (could be saved to database)
        # For now, just log it
        
        return response
    
    @app.get("/v1/evolution/status")
    async def get_evolution_status_simple(
        current_user: User = Depends(get_current_user)
    ):
        """
        Get simplified evolution status for HUD display.
        
        Shows what plugin JARVIS is planning to code next in app/plugins/dynamic.
        
        Returns:
            Evolution status with next plugin and count
        """
        try:
            from app.application.services.capability_manager import CapabilityManager
            
            # Initialize capability manager
            capability_manager = CapabilityManager(engine=db_adapter.engine)
            
            # Get next evolution step
            next_step = capability_manager.get_next_evolution_step()
            
            # Count dynamic plugins using the configured path
            plugins_dir = Path(PLUGINS_DYNAMIC_DIR)
            plugin_count = 0
            if plugins_dir.exists():
                plugin_count = len([f for f in plugins_dir.glob("*.py") if f.is_file()])
            
            if next_step:
                return {
                    "next_plugin": next_step["name"],
                    "status": "Planejando implementação",
                    "plugin_count": plugin_count,
                    "progress": next_step.get("progress", 0)
                }
            else:
                return {
                    "next_plugin": None,
                    "status": "Todas as capacidades implementadas ou aguardando recursos",
                    "plugin_count": plugin_count,
                    "progress": 100
                }
        
        except Exception as e:
            logger.error(f"Error getting evolution status: {e}")
            return {
                "next_plugin": None,
                "status": "Erro ao obter status",
                "plugin_count": 0,
                "error": str(e)
            }
    
    @app.get("/v1/roadmap/progress")
    async def get_roadmap_progress(
        current_user: User = Depends(get_current_user)
    ):
        """
        Get roadmap progress metrics for HUD display.
        
        Returns completion percentage based on ROADMAP.md missions.
        
        Returns:
            Roadmap progress with completion percentage
        """
        try:
            from app.application.services.auto_evolution import AutoEvolutionService
            
            # Initialize auto evolution service
            auto_evolution = AutoEvolutionService()
            
            # Get success metrics from roadmap
            metrics = auto_evolution.get_success_metrics()
            
            if 'error' in metrics:
                logger.error(f"Error getting roadmap metrics: {metrics['error']}")
                return {
                    "completion_percentage": 0.0,
                    "total_missions": 0,
                    "completed": 0,
                    "in_progress": 0,
                    "planned": 0,
                    "error": metrics['error']
                }
            
            return {
                "completion_percentage": metrics['completion_percentage'],
                "total_missions": metrics['total_missions'],
                "completed": metrics['completed'],
                "in_progress": metrics['in_progress'],
                "planned": metrics['planned']
            }
        
        except Exception as e:
            logger.error(f"Error getting roadmap progress: {e}")
            return {
                "completion_percentage": 0.0,
                "total_missions": 0,
                "completed": 0,
                "in_progress": 0,
                "planned": 0,
                "error": str(e)
            }

    return app
