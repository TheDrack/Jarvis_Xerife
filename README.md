# Jarvis Voice Assistant

A professional, modular voice assistant built with Python, featuring voice recognition, text-to-speech, and system automation capabilities.

## Features

- **Voice Recognition**: Brazilian Portuguese (pt-BR) voice commands using Google Speech Recognition
- **Text-to-Speech**: Natural voice synthesis with pyttsx3
- **System Automation**: Interface control using PyAutoGUI and Keyboard
- **Web Navigation**: Browser automation and URL handling
- **Modular Architecture**: Clean separation of concerns with extensible design
- **Docker Support**: Containerized deployment with Docker and Docker Compose
- **Airflow Integration**: Example DAGs for scheduled automation tasks
- **Type Safety**: Full type hinting throughout the codebase
- **Testing**: Pytest test suite with mocking support

## Project Structure

```
.
├── app/
│   ├── core/           # Core functionality
│   │   ├── engine.py   # JarvisEngine class
│   │   └── config.py   # Configuration management
│   ├── actions/        # Command actions
│   │   └── system_commands.py  # System automation
│   └── utils/          # Utility functions
├── tests/              # Pytest tests
│   └── test_engine.py
├── dags/               # Airflow DAGs
│   └── jarvis_status_dag.py
├── data/               # Static data files
├── logs/               # Log files
├── main.py             # Entry point
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker image definition
└── docker-compose.yml  # Docker orchestration
```

## Installation

### Local Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd python
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the assistant:
```bash
python main.py
```

### Docker Setup

1. Build and run with Docker Compose:
```bash
docker-compose up --build
```

2. Or build manually:
```bash
docker build -t jarvis-assistant .
docker run -it jarvis-assistant
```

## Configuration

Configuration is managed via `app/core/config.py` using pydantic-settings. You can customize settings by:

1. Creating a `.env` file in the project root
2. Setting environment variables
3. Modifying the Settings class defaults

Available settings:
- `APP_NAME`: Application name (default: "Jarvis Assistant")
- `LANGUAGE`: Recognition language (default: "pt-BR")
- `WAKE_WORD`: Activation phrase (default: "xerife")

## Usage

### Voice Commands

The assistant responds to the wake word "xerife" followed by commands:

- "xerife escreva [texto]" - Type text
- "xerife aperte [tecla]" - Press a key
- "xerife internet" - Open browser
- "xerife site [url]" - Open a website
- "fechar" - Exit the assistant

### Extending Functionality

The modular architecture allows easy extension:

1. **Add new actions**: Create new modules in `app/actions/`
2. **Custom commands**: Extend `CommandProcessor` in `system_commands.py`
3. **AI Integration**: Add AI modules for future Snake integration
4. **Web Scraping**: Create scraping modules in `app/actions/`

Example:
```python
# app/actions/my_custom_action.py
class MyCustomAction:
    def execute(self, param: str) -> None:
        # Your custom logic here
        pass
```

## Testing

Run tests with pytest:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_engine.py
```

## Airflow Integration

The project includes example Airflow DAGs in the `dags/` directory. To use with Airflow:

1. Install Airflow: `pip install apache-airflow`
2. Set AIRFLOW_HOME to point to this directory
3. Initialize the database: `airflow db init`
4. Start the scheduler: `airflow scheduler`
5. Start the webserver: `airflow webserver`

## Development

### Code Quality

The project follows professional Python standards:

- **Type Hints**: All functions use type annotations
- **Docstrings**: Google-style docstrings for all public methods
- **Linting**: Black, flake8, isort compatible
- **Testing**: Pytest with mocking support

### Running Code Quality Tools

```bash
# Format code
black app/ tests/

# Sort imports
isort app/ tests/

# Type checking
mypy app/

# Linting
flake8 app/ tests/
```

## License

This project is provided as-is for educational and personal use.

## Contributing

Future enhancements planned:
- Integration with custom AI models (Snake)
- Advanced web scraping capabilities
- Natural language processing improvements
- Multi-language support
- GUI interface

## Troubleshooting

### Audio Issues
If you encounter audio device errors:
- Ensure microphone permissions are granted
- Check PyAudio installation
- On Linux, install: `sudo apt-get install portaudio19-dev`

### Docker Audio
For audio in Docker containers:
- Uncomment device mappings in docker-compose.yml
- May require privileged mode for some systems

## Support

For issues and questions, please open an issue in the repository.
