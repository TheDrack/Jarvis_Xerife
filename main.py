#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Voice Assistant - Main Entry Point

A modular voice assistant with Hexagonal Architecture:
- Clean separation between Domain, Application, and Adapters
- Hardware-independent core logic (cloud-ready)
- Dependency injection for all external dependencies
- Support for Edge (local hardware) and Cloud deployments
"""

from app.bootstrap_edge import main

if __name__ == "__main__":
    main()
