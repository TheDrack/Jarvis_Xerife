# -*- coding: utf-8 -*-
import json
import os
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Crystallizer")

class CrystallizerEngine:
    def __init__(self, 
                 cap_path="data/capabilities.json", 
                 crystal_path="data/master_crystal.json", 
                 container_path="app/container.py"):

        self.paths = {
            "caps": Path(cap_path),
            "crystal": Path(crystal_path),
            "container": Path(container_path)
        }
        
        # Garante pastas base
        self.paths["caps"].parent.mkdir(parents=True, exist_ok=True)

        # Carrega Master Crystal ou inicia novo
        self.master_crystal = self._load_json(self.paths["crystal"]) or self._init_crystal()
        
        # Carrega Capabilities
        caps_data = self._load_json(self.paths["caps"])
        self.capabilities = caps_data.get('capabilities', []) if caps_data else []

    def _load_json(self, path: Path):
        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao ler JSON em {path}: {str(e)}")
        return None

    def _init_crystal(self):
        return {
            "system_id": "JARVIS_CORE",
            "version": "1.1.0",
            "last_scan": None,
            "registry": []
        }

    def _map_target(self, cap: Dict[str, Any]) -> str:
        title = cap.get('title', '').lower()
        desc = cap.get('description', '').lower()

        if any(x in title or x in desc for x in ["llm", "ai", "gear", "cognition", "groq"]):
            return "app/domain/gears/"
        if any(x in title or x in desc for x in ["model", "state", "entity", "schema"]):
            return "app/domain/models/"
        if any(x in title or x in desc for x in ["adapter", "web", "pyautogui", "os", "keyboard"]):
            return "app/adapters/"

        return "app/domain/capabilities/"

    def run_full_cycle(self):
        """Executa a tríade de cristalização em alta velocidade."""
        logger.info("🚀 Iniciando Ciclo de Cristalização JARVIS...")
        self.audit()
        self.transmute()
        self.stitch()
        self._save_crystal()
        logger.info("✨ Cristalização Concluída.")

    def audit(self):
        container_content = ""
        if self.paths["container"].exists():
            container_content = self.paths["container"].read_text(encoding='utf-8')

        new_registry = []
        for cap in self.capabilities:
            cap_id = cap['id']
            target_dir = self._map_target(cap)
            target_file = f"{cap_id.lower().replace('-', '_')}_core.py"
            target_path = os.path.join(target_dir, target_file)

            is_in_container = f'"{cap_id}"' in container_content
            is_physically_present = Path(target_path).exists()

            new_registry.append({
                "id": cap_id,
                "title": cap['title'],
                "status": "crystallized" if is_in_container and is_physically_present else "incomplete",
                "genealogy": {
                    "target_suggested": target_dir,
                    "target_file": target_path
                },
                "integration": {
                    "in_container": is_in_container,
                    "physically_present": is_physically_present
                }
            })
        self.master_crystal["registry"] = new_registry
        self.master_crystal["last_scan"] = datetime.now().isoformat()

    def transmute(self):
        for entry in self.master_crystal["registry"]:
            if not entry["integration"]["physically_present"]:
                t_path = Path(entry["genealogy"]["target_file"])
                t_dir = Path(entry["genealogy"]["target_suggested"])

                t_dir.mkdir(parents=True, exist_ok=True)
                (t_dir / "__init__.py").touch()

                with open(t_path, 'w', encoding='utf-8') as f:
                    f.write(f'# -*- coding: utf-8 -*-\n"""CAPABILITY: {entry["title"]}\nID: {entry["id"]}"""\n\ndef execute(context=None):\n    # JARVIS INITIAL STATE\n    return {{"status":
