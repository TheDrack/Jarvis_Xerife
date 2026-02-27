# -*- coding: utf-8 -*-
import json
import os
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Configuração de Log JARVIS
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)
logger = logging.getLogger("Crystallizer")

class CrystallizerEngine:
    """
    Motor de Cristalização JARVIS V3.2.
    Responsável por transmutar capacidades em arquivos físicos seguindo as regras de destino.
    """
    def __init__(self, cap_path="data/capabilities.json", crystal_path="data/master_crystal.json"):
        self.paths = {
            "caps": Path(cap_path),
            "crystal": Path(crystal_path),
            "app_dir": Path("app")
        }

        # Inicialização do Crystal (Bússola do Sistema)
        self.master_crystal = self._load_json(self.paths["crystal"]) or self._init_crystal()

        # Carregamento das capacidades
        caps_data = self._load_json(self.paths["caps"])
        self.source_capabilities = caps_data.get('capabilities', []) if caps_data else []

    def _load_json(self, path: Path):
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Erro ao ler JSON {path}: {e}")
        return None

    def _map_target(self, cap: Dict[str, Any]) -> str:
        """
        Mapeia o setor de destino baseado nas Regras de Cristalização (Palavras-chave).
        """
        title = cap.get('title', '').lower()
        id_cap = cap.get('id', '').lower()
        search_blob = f"{title} {id_cap}"

        # 1. ADAPTERS (Hardware, IO, Externos)
        if any(x in search_blob for x in ["pyautogui", "keyboard", "click", "press", "os", "file", "drive", "sqlite", "requests"]):
            return "app/infrastructure/adapters"

        # 2. DOMAIN GEARS (Raciocínio, LLMs, Seleção de Potência)
        if any(x in search_blob for x in ["llm", "reasoning", "cognitive", "router", "selector", "marcha", "potencia"]):
            return "app/domain/gears"

        # 3. APPLICATION SERVICES (Orquestração, Fluxo, Pontes)
        if any(x in search_blob for x in ["flow", "orchestration", "loop", "bridge", "service", "sync"]):
            return "app/application/services"

        # 4. DOMAIN CAPABILITIES (Regras de Negócio e Validação)
        return "app/domain/capabilities"

    def transmute(self):
        """Garante a existência física seguindo o contrato NexusComponent aprimorado."""
        for cap in self.source_capabilities:
            target_dir = Path(self._map_target(cap))
            target_file = f"{cap['id'].lower().replace('-', '_')}.py"
            target_path = target_dir / target_file

            if not target_path.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                
                # Formatação do nome da Classe (CamelCase)
                class_name = "".join(word.capitalize() for word in cap['id'].replace('-', '_').split("_"))

                content = (
                    "# -*- coding: utf-8 -*-\n"
                    "from app.core.nexuscomponent import NexusComponent\n\n"
                    f"class {class_name}(NexusComponent):\n"
                    "    \"\"\"\n"
                    f"    Capacidade: {cap.get('title')}\n"
                    "    ID: {cap['id']}\n"
                    "    Setor: {target_dir}\n"
                    "    \"\"\"\n\n"
                    "    def __init__(self):\n"
                    "        super().__init__()\n"
                    "        # Padrões iniciais do componente\n"
                    "        self.active = True\n\n"
                    "    def configure(self, config: dict = None):\n"
                    "        \"\"\"Opcional: Configuração via Pipeline YAML\"\"\"\n"
                    "        if config:\n"
                    "            pass\n\n"
                    "    def execute(self, context: dict = None):\n"
                    "        \"\"\"Execução lógica principal\"\"\"\n"
                    f"        print('🚀 Executando {class_name}...')\n"
                    f"        return {{'status': 'success', 'id': '{cap['id']}'}}\n"
                )
                target_path.write_text(content, encoding='utf-8')
                logger.info(f"💎 Cristalizado: {target_path}")

    def audit_and_link(self):
        """Mapeia o DNA e atualiza o Registro para o Nexus."""
        new_registry = []
        for cap in self.source_capabilities:
            cap_id = cap['id']
            target_dir = self._map_target(cap)
            target_file_name = f"{cap_id.lower().replace('-', '_')}.py"
            target_path = Path(target_dir) / target_file_name

            new_registry.append({
                "id": cap_id,
                "title": cap.get('title'),
                "status": "active" if target_path.exists() else "pending",
                "path": str(target_path).replace("\\", "/"),
                "sector": target_dir.split("/")[-1],
                "last_audit": datetime.now().isoformat()
            })
        self.master_crystal["registry"] = new_registry

    def _save_crystal(self):
        self.master_crystal["last_scan"] = datetime.now().isoformat()
        self.paths["crystal"].parent.mkdir(parents=True, exist_ok=True)
        with open(self.paths["crystal"], 'w', encoding='utf-8') as f:
            json.dump(self.master_crystal, f, indent=4, ensure_ascii=False)
        logger.info(f"🔮 Master Crystal atualizado.")

    def _init_crystal(self):
        return {"system_id": "JARVIS_CORE", "version": "3.2.0", "registry": []}

    def run_full_cycle(self):
        logger.info("🚀 Iniciando Ciclo de Cristalização Nexus...")
        self.transmute()
        self.audit_and_link()
        self._save_crystal()
        logger.info("✅ DNA Cristalizado e Sincronizado.")

if __name__ == "__main__":
    CrystallizerEngine().run_full_cycle()
