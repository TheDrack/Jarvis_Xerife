# Extensibility Guide

This guide explains how to extend Jarvis Assistant with new functionality using the **Hexagonal Architecture** pattern.

> **Note**: For the legacy action-based approach (deprecated), see the end of this document.

## Adding New Commands (Hexagonal Architecture)

The recommended way to add new functionality follows the Ports and Adapters pattern. See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

### 1. Add New Command Type (Domain Layer)

First, add a new command type to the domain:

```python
# In app/domain/models/command.py
class CommandType(Enum):
    # ... existing types
    SCREENSHOT = "screenshot"
    SEND_EMAIL = "send_email"
    # Your new command type
```

### 2. Update Command Interpreter (Domain Layer)

Add pattern matching for your new command:

```python
# In app/domain/services/command_interpreter.py
class CommandInterpreter:
    def __init__(self, wake_word: str = "jarvis"):
        # ...
        self._command_patterns = {
            # ... existing patterns
            r"(tire|capture|print)\s+(foto|screenshot|tela)": CommandType.SCREENSHOT,
        }
```

### 3. Define Port Interface (Application Layer) - If Needed

If your command requires new capabilities not covered by existing ports, define a new interface:

```python
# In app/application/ports/screenshot_provider.py
from abc import ABC, abstractmethod
from pathlib import Path

class ScreenshotProvider(ABC):
    """Port for screenshot capabilities"""
    
    @abstractmethod
    def capture_screen(self, filepath: Path) -> bool:
        """
        Capture screenshot
        
        Args:
            filepath: Where to save the screenshot
            
        Returns:
            True if successful
        """
        pass
```

### 4. Create Adapter Implementation (Adapters Layer)

Implement the concrete adapter:

```python
# In app/adapters/edge/screenshot_adapter.py
from pathlib import Path
from PIL import ImageGrab
from app.application.ports.screenshot_provider import ScreenshotProvider

class ScreenshotAdapter(ScreenshotProvider):
    """Edge adapter for taking screenshots"""
    
    def capture_screen(self, filepath: Path) -> bool:
        """Capture screenshot using PIL"""
        try:
            screenshot = ImageGrab.grab()
            screenshot.save(filepath)
            return True
        except Exception as e:
            print(f"Screenshot failed: {e}")
            return False
```

### 5. Update Container (Dependency Injection)

Register your new adapter in the container:

```python
# In app/container.py
from app.adapters.edge.screenshot_adapter import ScreenshotAdapter

@dataclass
class Container:
    # ... existing providers
    screenshot_provider: ScreenshotProvider
    # ...

def create_edge_container(
    wake_word: str = "jarvis",
    language: str = "pt-BR",
    use_llm: bool = False
) -> Container:
    # ... existing code
    screenshot_provider = ScreenshotAdapter()
    
    return Container(
        # ... existing providers
        screenshot_provider=screenshot_provider,
        # ...
    )
```

### 6. Update AssistantService (Application Layer)

Add execution logic to the assistant service:

```python
# In app/application/services/assistant_service.py
class AssistantService:
    def __init__(
        self,
        # ... existing parameters
        screenshot_provider: ScreenshotProvider,
    ):
        # ... existing code
        self.screenshot = screenshot_provider
    
    def _execute_command(self, command: Command) -> Response:
        """Execute a validated command"""
        # ... existing code
        
        elif command.command_type == CommandType.SCREENSHOT:
            filepath = Path(command.parameters.get("filepath", "screenshot.png"))
            success = self.screenshot.capture_screen(filepath)
            return Response(
                success=success,
                message=f"Screenshot saved to {filepath}" if success else "Screenshot failed"
            )
```

## Adding LLM Functions

If using LLM integration, add functions to the agent service:

```python
# In app/domain/services/agent_service.py
def get_function_declarations(self) -> List[Dict[str, Any]]:
    """Get function schemas for Gemini"""
    return [
        # ... existing functions
        {
            "name": "take_screenshot",
            "description": "Captura uma imagem da tela atual",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Nome do arquivo para salvar (ex: screenshot.png)"
                    }
                },
                "required": ["filename"]
            }
        }
    ]

def map_function_to_command_type(self, function_name: str) -> Optional[CommandType]:
    """Map Gemini function name to CommandType"""
    mapping = {
        # ... existing mappings
        "take_screenshot": CommandType.SCREENSHOT,
    }
    return mapping.get(function_name)
```

## Integrating AI Models

To integrate custom AI models or ML models using hexagonal architecture:

### 1. Define Port Interface

```python
# In app/application/ports/ml_provider.py
from abc import ABC, abstractmethod
from typing import Any, Dict

class MLProvider(ABC):
    """Port for machine learning model integration"""
    
    @abstractmethod
    def predict(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make prediction using ML model
        
        Args:
            input_data: Input data for the model
            
        Returns:
            Prediction results
        """
        pass
```

### 2. Create Adapter

```python
# In app/adapters/infrastructure/custom_ml_adapter.py
from typing import Any, Dict
from app.application.ports.ml_provider import MLProvider

class CustomMLAdapter(MLProvider):
    """Adapter for custom ML model"""
    
    def __init__(self, model_path: str):
        """Initialize with model path"""
        self.model = self._load_model(model_path)
    
    def _load_model(self, path: str) -> Any:
        """Load the ML model"""
        # Use your preferred ML framework (TensorFlow, PyTorch, etc.)
        import joblib  # or tensorflow, torch, etc.
        return joblib.load(path)
    
    def predict(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Make prediction"""
        # Preprocess input
        features = self._preprocess(input_data)
        
        # Make prediction
        result = self.model.predict(features)
        
        # Return formatted result
        return {"prediction": result.tolist(), "confidence": 0.95}
    
    def _preprocess(self, data: Dict[str, Any]) -> Any:
        """Preprocess input data"""
        # Your preprocessing logic
        pass
```

### 3. Inject in Container

```python
# In app/container.py
ml_provider = CustomMLAdapter(model_path="path/to/model.pkl")
container = Container(
    # ... other providers
    ml_provider=ml_provider,
)
```

### 4. Use in AssistantService

```python
# Add new command type for ML predictions
# Then in AssistantService:
elif command.command_type == CommandType.PREDICT:
    input_data = command.parameters
    result = self.ml_provider.predict(input_data)
    return Response(
        success=True,
        message=f"Prediction: {result['prediction']}",
        data=result
    )
```

## Web Scraping Integration

To add web scraping functionality using hexagonal architecture:

### 1. Define Port

```python
# In app/application/ports/scraper_provider.py
from abc import ABC, abstractmethod
from typing import List

class ScraperProvider(ABC):
    """Port for web scraping capabilities"""
    
    @abstractmethod
    def scrape_page(self, url: str, selector: str) -> List[str]:
        """
        Scrape data from a web page
        
        Args:
            url: URL to scrape
            selector: CSS selector for data
            
        Returns:
            List of scraped text data
        """
        pass
```

### 2. Create Adapter

```python
# In app/adapters/infrastructure/scraper_adapter.py
from typing import List
import requests
from bs4 import BeautifulSoup
from app.application.ports.scraper_provider import ScraperProvider

class ScraperAdapter(ScraperProvider):
    """Infrastructure adapter for web scraping"""
    
    def __init__(self):
        """Initialize scraper with session"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; JarvisBot/1.0)'
        })
    
    def scrape_page(self, url: str, selector: str) -> List[str]:
        """Scrape data from web page using BeautifulSoup"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            elements = soup.select(selector)
            
            return [elem.get_text(strip=True) for elem in elements]
        except Exception as e:
            print(f"Scraping failed: {e}")
            return []
```

### 3. Inject and Use

```python
# In container.py and AssistantService
scraper_provider = ScraperAdapter()

# In AssistantService._execute_command:
elif command.command_type == CommandType.SCRAPE:
    url = command.parameters.get("url")
    selector = command.parameters.get("selector", "p")
    results = self.scraper.scrape_page(url, selector)
    return Response(
        success=len(results) > 0,
        message=f"Found {len(results)} items",
        data={"items": results}
    )
```

## Adding Custom DAGs

Create new Airflow DAGs in the `dags/` directory using the hexagonal architecture:

```python
# dags/my_custom_dag.py
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

def my_task():
    """Task implementation using Jarvis services"""
    from app.container import create_edge_container
    
    # Create container with dependencies
    container = create_edge_container()
    assistant = container.assistant_service
    
    # Execute command programmatically
    response = assistant.process_command("escreva automated task")
    print(f"Result: {response.message}")

dag = DAG(
    'my_custom_workflow',
    default_args={'start_date': datetime(2024, 1, 1)},
    schedule_interval=timedelta(days=1),
)

task = PythonOperator(
    task_id='my_task',
    python_callable=my_task,
    dag=dag,
)
```

## Testing New Features

Follow hexagonal architecture testing patterns:

### Domain Tests (No Mocks Needed)

```python
# tests/domain/test_my_domain_service.py
import pytest
from app.domain.services.my_service import MyService
from app.domain.models.command import CommandType

def test_my_domain_logic():
    """Test pure domain logic"""
    service = MyService()
    result = service.process_data("test input")
    
    assert result is not None
    assert result.success
```

### Application Tests (With Mocked Ports)

```python
# tests/application/test_my_feature.py
import pytest
from unittest.mock import Mock
from app.application.services.assistant_service import AssistantService
from app.domain.models.command import CommandType, Command

def test_new_command_execution():
    """Test command execution with mocked dependencies"""
    # Mock the ports
    mock_provider = Mock()
    mock_provider.execute.return_value = True
    
    # Create service with mocked dependencies
    service = AssistantService(
        # ... inject mocked providers
        custom_provider=mock_provider,
    )
    
    # Execute command
    command = Command(command_type=CommandType.MY_NEW_TYPE, parameters={})
    response = service._execute_command(command)
    
    assert response.success
    mock_provider.execute.assert_called_once()
```

### Adapter Tests

```python
# tests/adapters/test_my_adapter.py
import pytest
from app.adapters.edge.my_adapter import MyAdapter

def test_adapter_implementation():
    """Test adapter concrete implementation"""
    adapter = MyAdapter()
    result = adapter.execute("test")
    
    assert result is not None
```

## Configuration

Add new configuration options in `app/core/config.py`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ... existing settings ...
    
    # Your new settings
    my_feature_enabled: bool = True
    my_api_key: Optional[str] = None
    my_model_path: str = "models/default.pkl"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
```

## Best Practices

### Hexagonal Architecture

1. **Domain First**: Start with pure domain logic (no dependencies)
2. **Define Ports**: Create interfaces for external dependencies
3. **Implement Adapters**: Create concrete implementations in adapters/
4. **Dependency Injection**: Register in container.py
5. **Test at Each Layer**: Domain tests need no mocks, application tests mock ports

### Code Quality

1. **Type Hints**: Always use type annotations
2. **Documentation**: Add Google-style docstrings to all public methods
3. **Testing**: Write tests for domain, application, and adapter layers
4. **Modularity**: Keep modules focused and independent
5. **Configuration**: Use the Settings class with pydantic-settings
6. **Logging**: Use Python's logging module consistently

### Architecture Guidelines

- **Never** import adapters in domain layer
- **Never** import infrastructure in application layer (except ports)
- **Always** use dependency injection
- **Always** test domain logic without mocks
- **Prefer** small, focused adapters over large monolithic ones

---

## Legacy Approach (Deprecated)

> **Note**: The following approach using `app/actions/` is deprecated. Use the hexagonal architecture approach described above for new features.

For maintaining compatibility with legacy code in `app/actions/`, you can still extend using the old pattern, but this is not recommended for new development. See git history for examples of the legacy approach.
