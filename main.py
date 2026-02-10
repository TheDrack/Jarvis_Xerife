import os
import logging
import uvicorn
from app.adapters.infrastructure.api_server import create_api_server
from app.container import create_edge_container
from app.core.config import settings

# Import plugin loader for auto-extensibility
from app.plugins.plugin_loader import load_plugins

logger = logging.getLogger(__name__)

def start_cloud():
    """Inicializa o Jarvis em modo API para o Render/Nuvem"""
    
    # Auto-load dynamic plugins for extensibility
    try:
        loaded_plugins = load_plugins()
        logger.info(f"🔌 Loaded {len(loaded_plugins)} dynamic plugin(s)")
    except Exception as e:
        logger.warning(f"Plugin loading failed: {e}")
    
    # Usa o Container para instanciar o AssistantService com todas as dependências
    # Note: create_edge_container will auto-enable LLM if API key is available
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
    )
    
    # Obtém a instância configurada do AssistantService
    assistant_service = container.assistant_service
    
    # Cria a aplicação FastAPI com o serviço
    app = create_api_server(assistant_service)
    
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Jarvis Online na Nuvem - Porta {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    if os.getenv("PORT"):
        start_cloud()
    else:
        from app.bootstrap_edge import main
        main()
