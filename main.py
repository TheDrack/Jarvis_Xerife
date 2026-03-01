#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Assistant - Main Entry Point (Edge/Local deployment)

Starts the Jarvis Assistant in edge mode with hardware support.
This is the main entry point used by Docker edge stage (CMD ["python", "main.py"]).
"""

import os
import sys

import uvicorn

from app.adapters.infrastructure import create_api_server
from app.bootstrap_edge import main as edge_main
from app.container import create_edge_container
from app.core.config import settings


def start_cloud():
    """
    Cloud/server entry point for API mode.
    Kept for backward compatibility with tests that import main.start_cloud().
    """
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
    )
    assistant = container.assistant_service
    app = create_api_server(assistant)
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)


if __name__ == "__main__":
    edge_main()
