#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Voice Assistant - API Server Entry Point

Starts the FastAPI server for headless control interface.
This entry point initializes the assistant service with edge container
and exposes it via REST API for remote control.
"""

import logging
import os
import sys

import uvicorn

from app.adapters.infrastructure import create_api_server
from app.container import create_edge_container
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.logs_dir / "jarvis_api.log"),
    ],
)

logger = logging.getLogger(__name__)


def main() -> None:
    """
    Main entry point for API server.
    Initializes the assistant service and starts the FastAPI server.
    """
    logger.info("Starting Jarvis Assistant API Server (Headless Mode)")
    logger.info(f"Wake word: {settings.wake_word}")
    logger.info(f"Language: {settings.language}")

    # Headless safety: Set environment variables to prevent GUI windows
    # This prevents PyAutoGUI and other libraries from showing error dialogs
    os.environ["DISPLAY"] = os.environ.get("DISPLAY", "")
    if not os.environ.get("DISPLAY"):
        logger.info("Running in headless mode (no DISPLAY set)")

    # Create container with edge adapters
    # Note: use_llm can be controlled via environment variable
    use_llm = os.getenv("USE_LLM", "false").lower() in ("true", "1", "yes")
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
        use_llm=use_llm,
    )

    # Get the assistant service
    assistant = container.assistant_service

    # Check adapter availability (but don't fail - API can still work)
    try:
        if hasattr(assistant.voice, "is_available") and not assistant.voice.is_available():
            logger.warning(
                "Voice recognition not available - API will work but voice features may be limited"
            )
    except Exception as e:
        logger.warning(f"Could not check voice availability: {e}")

    try:
        if hasattr(assistant.action, "is_available") and not assistant.action.is_available():
            logger.warning(
                "Action automation not available - "
                "API will work but automation may be limited"
            )
    except Exception as e:
        logger.warning(f"Could not check action availability: {e}")

    # Create FastAPI application
    app = create_api_server(assistant)

    # Get server configuration from environment
    # Render uses PORT, but support API_PORT for backward compatibility
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))

    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"API Documentation available at http://localhost:{port}/docs")

    # Start uvicorn server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt - shutting down")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
