#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Setor: Project Root
Responsabilidade: Metadados de instalação.
"""
from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name="jarvis-assistant",
    version="1.1.0",
    description="Sistema Simbiótico Jarvis - Orquestração via Nexus",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="TheDrack",
    python_requires=">=3.9",
    packages=find_packages(exclude=["tests*"]),
    install_requires=[
        "pydantic>=2.0.0",
        "google-genai",
        "fastapi>=0.104.0",
        "sqlmodel>=0.0.14",
    ],
    extras_require={
        "edge": ["pyautogui", "speechrecognition", "pynput"],
    }
)
