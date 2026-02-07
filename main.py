import os
import uvicorn
from app.adapters.infrastructure.api_server import create_api_server
# Importamos o cara que sabe montar o AssistantService
from app.application.dependency_manager import DependencyManager 

def start_cloud():
    """Inicializa o Jarvis em modo API para o Render/Nuvem"""
    
    # 1. O DependencyManager monta todas as 5 dependências (voice, action, etc.)
    # baseado nas configurações do seu settings/env
    manager = DependencyManager()
    assistant_service = manager.get_assistant_service()
    
    # 2. Agora o Factory recebe o serviço completo e feliz
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
