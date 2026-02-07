#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Setup script for Jarvis Assistant"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name="jarvis-assistant",
    version="1.0.0",
    description="A professional voice assistant with system automation capabilities",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="TheDrack",
    python_requires=">=3.9",
    packages=find_packages(exclude=["tests", "tests.*"]),
    install_requires=[
        # Core cloud-ready dependencies only
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "python-dotenv>=1.0.0",
        "google-generativeai>=0.3.0",
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "python-multipart>=0.0.6",
        "python-jose[cryptography]>=3.3.0",
        "passlib[bcrypt]>=1.7.4",
        "cryptography>=41.0.0",
        "sqlmodel>=0.0.14",
    ],
    extras_require={
        "edge": [
            # Hardware and automation dependencies for edge deployment
            "pyttsx3>=2.90",
            "SpeechRecognition>=3.10.0",
            "PyAutoGUI>=0.9.54",
            "pynput>=1.7.6",
            "pyperclip>=1.8.2",
            "pandas>=2.0.0",
            "openpyxl>=3.1.0",
        ],
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.11.1",
            "mypy>=1.5.0",
            "black>=23.7.0",
            "flake8>=6.1.0",
            "isort>=5.12.0",
        ],
        "airflow": [
            "apache-airflow>=2.7.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "jarvis=app.bootstrap_edge:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
