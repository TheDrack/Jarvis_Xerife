import os
import shutil
from pathlib import Path

# Definição do Mapa de Cristalização baseado nas suas regras
RULES = {
    "src/adapters": {
        "keywords": ["pyautogui", "keyboard", "sqlite", "requests", "os", "shutil", "websockets"],
        "files": ["jarvis_local_agent.py", "worker_pc.py"]
    },
    "src/domain/gears": {
        "keywords": ["llm_reasoning", "cognitive_router", "model_selector", "google-genai"],
        "files": []
    },
    "src/domain/capabilities": {
        "keywords": ["business_logic", "validation", "inventory_management", "mission_selector"],
        "files": ["mission_selector.py"]
    },
    "src/application/services": {
        "keywords": ["flow", "orchestration", "loop", "bridge", "serve", "main"],
        "files": ["serve.py", "main.py"]
    }
}

def cristalizar():
    base_path = Path(".")
    
    # 1. Criar estrutura de pastas se não existir
    for folder in RULES.keys():
        os.makedirs(folder, exist_ok=True)

    # 2. Varrer arquivos da raiz e organizar
    for file_path in base_path.glob("*.py"):
        if file_path.name == "setup.py" or file_path.name.startswith("."):
            continue
            
        content = file_path.read_text(errors='ignore').lower()
        moved = False

        # Tenta classificar por arquivos explícitos ou palavras-chave
        for target_dir, criteria in RULES.items():
            if file_path.name in criteria["files"] or any(k in content for k in criteria["keywords"]):
                dest = Path(target_dir) / file_path.name
                print(f"[JARVIS] Movendo {file_path.name} -> {target_dir}")
                shutil.move(str(file_path), str(dest))
                moved = True
                break
    
    # 3. Tratamento especial para o arquivo consolidado se ele existir
    if os.path.exists("CORE_LOGIC_CONSOLIDATED.txt"):
        os.makedirs("docs/architecture", exist_ok=True)
        shutil.move("CORE_LOGIC_CONSOLIDATED.txt", "docs/architecture/CORE_LOGIC_CONSOLIDATED.txt")

if __name__ == "__main__":
    cristalizar()
