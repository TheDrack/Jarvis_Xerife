#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Assistant - Main Entry Point (Edge/Local deployment)

Starts the Jarvis Assistant in edge mode with hardware support.
This is the main entry point used by Docker edge stage (CMD ["python", "main.py"]).
"""

from app.bootstrap_edge import main

if __name__ == "__main__":
    main()
