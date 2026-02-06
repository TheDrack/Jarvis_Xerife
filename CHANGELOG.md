# Changelog

All notable changes to the Jarvis Assistant project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

#### Documentation
- Updated installation documentation to reflect simplified build process
- Enhanced README.md with clearer installation options (Installer Executable, Python, Manual)
- Improved INSTALLER_README.md with detailed build instructions and troubleshooting
- Emphasized the ease of using the standalone executable installer
- Added notes about PyInstaller onefile mode and automated GitHub Actions builds

## [1.0.0] - 2024-02-05

### Added

#### Core Features
- Complete refactoring from monolithic `assistente.pyw` to professional modular architecture
- `JarvisEngine` class for voice recognition and text-to-speech
- `SystemCommands` class for interface automation (PyAutoGUI/Keyboard)
- `WebNavigator` class for web browser automation
- `CommandProcessor` for routing voice commands to appropriate handlers
- Configuration management with pydantic-settings
- Type hints throughout the entire codebase

#### Project Structure
- Professional folder structure (app/core, app/actions, app/utils, tests, data, dags)
- README.md files in each module explaining responsibilities
- Main entry point via `main.py`

#### DevOps & Infrastructure
- Dockerfile for containerization
- docker-compose.yml for orchestration
- Airflow DAG example for workflow automation
- Makefile for common development tasks

#### Testing & Quality
- Comprehensive pytest test suite (24 tests, 100% passing)
- Test fixtures in conftest.py
- pytest configuration with coverage reporting
- mypy configuration for type checking
- Code formatting with Black and isort
- Test coverage reporting

#### Documentation
- Comprehensive README.md with usage instructions
- EXTENSIBILITY.md guide for adding new features
- CONTRIBUTING.md for development guidelines
- Project structure documentation
- Inline documentation with Google-style docstrings

#### Development Tools
- setup.py for package management
- requirements.txt with all dependencies
- .gitignore for Python projects
- .env.example for configuration template
- Utility helper functions (logging, file operations)

### Changed
- Migrated from procedural code to object-oriented architecture
- Separated concerns into distinct modules
- Improved error handling and type safety

### Removed
- Work-specific functions (4R system integration)
- Almoxarifado-specific functionality
- Material requisition features
- Cost center management
- All hard-coded file paths and credentials
- Excel spreadsheet dependencies for commands

### Security
- Removed hard-coded credentials
- Added configuration management for sensitive data
- Improved input validation and error handling

## [0.1.0] - Original

### Initial Release
- Basic voice recognition in Portuguese (pt-BR)
- Text-to-speech functionality
- PyAutoGUI automation
- Work-specific integrations

[1.0.0]: https://github.com/TheDrack/python/releases/tag/v1.0.0
[0.1.0]: https://github.com/TheDrack/python/releases/tag/v0.1.0
