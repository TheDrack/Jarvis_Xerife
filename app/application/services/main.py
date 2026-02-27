import os
import json
from app.core.nexus import JarvisNexus

def bootstrap():
    # 1. Instanciar o Nexus (O coração do projeto)
    nexus = JarvisNexus()
    
    # 2. Carregar o registro de componentes (conforme o data/nexus_registry.json anterior)
    # Aqui o Nexus descobre onde estão os Gears, Adapters e Services
    with open("data/nexus_registry.json", "r") as f:
        registry = json.load(f)
    
    # 3. Registrar componentes dinamicamente no Nexus
    for name, path in registry["components"].items():
        # O NexusComponent é instanciado e configurado aqui
        # (Assumindo que seu JarvisNexus já faz o import dinâmico)
        nexus.register_component(name, path)

    # 4. Preparar o Contexto Inicial (Protocolo JARVIS)
    context = {
        "env": os.environ,
        "artifacts": {},
        "metadata": {
            "user_input": input("Senhor, qual a sua ordem? "),
            "session_id": "jarvis_session_001"
        }
    }

    # 5. Executar o Orquestrador (Application Service)
    # Ele é quem conhece a ordem de execução dos Gears e Soldados
    orchestrator = nexus.get_component("orchestrator")
    orchestrator.configure(nexus) # Passa o Nexus para ele buscar os outros
    
    final_context = orchestrator.execute(context)

    # 6. Saída para a Interface
    print(f"\n[JARVIS]: {final_context['artifacts'].get('final_speech')}")

if __name__ == "__main__":
    bootstrap()
