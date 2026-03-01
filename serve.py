#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Assistant - API Server Entry Point (Cloud/Render deployment)

Starts the FastAPI server for headless control interface.
This is the main entry point used by Render (startCommand: python serve.py)
and Docker cloud stage (CMD ["python", "serve.py"]).
"""

from app.application.services.serve import main

if __name__ == "__main__":
    main()
