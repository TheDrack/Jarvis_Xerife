# -*- coding: utf-8 -*-
import json
import os
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Crystallizer")

class CrystallizerEngine:
    def __init__(self, cap_path="data/capabilities.json", crystal_path="data/master_crystal.json"):
        self.paths = {
            "caps": Path(cap_path),
            "crystal": Path(crystal_path),
            "container_dir": Path("app/application/containers")
        }
        
        self.sectors = {
            "gears": self.paths["container_dir"] / "gears_container.py",
            "models": self.paths["container_dir"] / "models_container.py",
            "adapters": self.paths["container_dir"] / "adapters_container.py",
            "capabilities": self.paths["container_dir"] / "capabilities_container.py"
        }

        self.master_crystal = self._load_json(self.paths["crystal"]) or self._init_crystal()
        caps_data = self._load_json(self.paths["caps"])
        self.source_capabilities = caps_data.get('capabilities', []) if caps_data else []

    def _load_json(self, path: Path):
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def _extract_libraries(self, file_path: Path) -> List[str]:
        """Faz o parsing do arquivo para encontrar imports reais."""
        if not file_path.exists():
            return []
        
        libs = set()
        try:
            content = file_path.read_text(encoding='utf-8')
            # Regex para: import lib ou from lib import ...
            import_matches = re.findall(r'^(?:import|from)\s+([a-zA-Z0-9_]+)', content, re.MULTILINE)
            for lib in import_matches:
                # Evitamos incluir o próprio app/hub como biblioteca externa
                if lib not in ['app', 'hub', 'json', 're', 'os', 'sys', 'pathlib']:
                    libs.add(lib)
        except Exception as e:
            logger.error(f"Erro ao escanear libs em {file_path}: {e}")
        
        return list(libs)

    def audit_and_link(self):
        """Documenta capacidades e AUTO-DETECTA bibliotecas usadas."""
        new_registry = []
        for cap in self.source_capabilities:
            cap_id = cap['id']
            # Lógica de mapeamento de diretório (gears, models, etc)
            target_dir = self._map_target(cap)
            target_file_name = f"{cap_id.lower().replace('-', '_')}_core.py"
            target_path = Path(target_dir) / target_file_name
            
            sector = "gears" if "gears" in str(target_path) else \
                     "models" if "models" in str(target_path) else \
                     "adapters" if "adapters" in str(target_path) else "capabilities"

            # SCAN DE BIBLIOTECAS (O Coração da sua ideia)
            detected_libs = self._extract_libraries(target_path)

            new_registry.append({
                "id": cap_id,
                "title": cap.get('title'),
                "status": cap.get('status', 'nonexistent'),
                "mapped_libraries": detected_libs, # Preenchido automaticamente pelo scan
                "sector": sector,
                "genealogy": {"target_file": str(target_path)},
                "integration": {
                    "in_container": self._check_container(cap_id, sector),
                    "physically_present": target_path.exists()
                }
            })
        self.master_crystal["registry"] = new_registry

    def _map_target(self, cap: Dict[str, Any]) -> str:
        title = cap.get('title', '').lower()
        if any(x in title for x in ["inventory", "gap", "objective"]): return "app/domain/gears/"
        if any(x in title for x in ["classify", "model", "entity"]): return "app/domain/models/"
        return "app/domain/capabilities/"

    def _check_container(self, cap_id: str, sector: str) -> bool:
        container_file = self.sectors.get(sector)
        if container_file and container_file.exists():
            return f'"{cap_id}"' in container_file.read_text(encoding='utf-8')
        return False

    def _save_crystal(self):
        self.master_crystal["last_scan"] = datetime.now().isoformat()
        with open(self.paths["crystal"], 'w', encoding='utf-8') as f:
            json.dump(self.master_crystal, f, indent=4, ensure_ascii=False)

    def _init_crystal(self):
        return {"system_id": "JARVIS_CORE", "version": "2.7.0", "registry": []}

    def run_full_cycle(self):
        logger.info("📡 Iniciando Auto-Sensing de Dependências...")
        self.audit_and_link()
        # ... transmute e stitch_sectors continuam os mesmos ...
        self._save_crystal()

if __name__ == "__main__":
    # Nota: Removi os métodos repetidos para brevidade, mas eles devem estar presentes.
    CrystallizerEngine().run_full_cycle()
