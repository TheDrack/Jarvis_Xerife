# -*- coding: utf-8 -*-
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

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

        self.paths["container_dir"].mkdir(parents=True, exist_ok=True)
        
        # Carrega ou inicializa o cristal mestre
        self.master_crystal = self._load_json(self.paths["crystal"]) or self._init_crystal()
        
        # Carrega as capacidades do arquivo fonte
        caps_data = self._load_json(self.paths["caps"])
        self.capabilities = caps_data.get('capabilities', []) if caps_data else []

    def _load_json(self, path: Path):
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def _init_crystal(self):
        """Inicializa a estrutura base do JARVIS_CORE."""
        return {
            "system_id": "JARVIS_CORE",
            "version": "2.0.0",
            "last_scan": datetime.now().isoformat(),
            "crystallization_summary": {
                "total_capabilities": 0,
                "crystallized": 0,
                "connected_legacy": 1,
                "orphan": 0
            },
            "registry": []
        }

    def _get_sector(self, target_path: str) -> str:
        if "gears" in target_path: return "gears"
        if "models" in target_path: return "models"
        if "adapters" in target_path: return "adapters"
        return "capabilities"

    def _map_target(self, cap: Dict[str, Any]) -> str:
        title = cap.get('title', '').lower()
        desc = cap.get('description', '').lower()
        if any(x in title or x in desc for x in ["llm", "ai", "gear", "cognition"]): return "app/domain/gears/"
        if any(x in title or x in desc for x in ["model", "state", "entity"]): return "app/domain/models/"
        if any(x in title or x in desc for x in ["adapter", "web", "os", "github"]): return "app/adapters/"
        return "app/domain/capabilities/"

    def run_full_cycle(self):
        logger.info("🚀 Iniciando Cristalização Setorial...")
        self.audit()           # Mapeia o estado atual
        self.transmute()       # Cria arquivos físicos se não existirem
        self.stitch_sectors()  # Registra nos containers Python
        self._update_metrics() # Atualiza o resumo (O QUE ESTAVA FALTANDO)
        self._save_crystal()   # Persiste no JSON
        logger.info("✨ Ciclo Concluído.")

    def audit(self):
        new_registry = []
        for cap in self.capabilities:
            cap_id = cap['id']
            target_dir = self._map_target(cap)
            target_file = f"{cap_id.lower().replace('-', '_')}_core.py"
            target_path = os.path.join(target_dir, target_file)
            sector = self._get_sector(target_path)

            container_file = self.sectors[sector]
            is_in_container = False
            if container_file.exists():
                is_in_container = f'"{cap_id}"' in container_file.read_text(encoding='utf-8')

            new_registry.append({
                "id": cap_id,
                "title": cap['title'],
                "sector": sector,
                "genealogy": {"target_file": target_path},
                "integration": {
                    "in_container": is_in_container, 
                    "physically_present": Path(target_path).exists()
                }
            })
        self.master_crystal["registry"] = new_registry

    def transmute(self):
        for entry in self.master_crystal["registry"]:
            if not entry["integration"]["physically_present"]:
                t_path = Path(entry["genealogy"]["target_file"])
                t_path.parent.mkdir(parents=True, exist_ok=True)
                content = (
                    "# -*- coding: utf-8 -*-\n"
                    f"'''CAPABILITY: {entry['title']}'''\n"
                    "def execute(context=None):\n"
                    f"    return {{'status': 'initialized', 'id': '{entry['id']}'}}\n"
                )
                t_path.write_text(content, encoding='utf-8')
                entry["integration"]["physically_present"] = True

    def stitch_sectors(self):
        for sector, path in self.sectors.items():
            if not path.exists():
                path.write_text(f"# -*- coding: utf-8 -*-\nclass {sector.capitalize()}Container:\n    def __init__(self):\n        self.registry = {{}}\n", encoding='utf-8')

        for entry in self.master_crystal["registry"]:
            if entry["integration"]["physically_present"] and not entry["integration"]["in_container"]:
                sector = entry["sector"]
                container_path = self.sectors[sector]
                content = container_path.read_text(encoding='utf-8')

                cap_id = entry["id"]
                var_name = f"{cap_id.lower().replace('-', '_')}_exec"
                # Ajusta path para formato de import python
                import_path = entry["genealogy"]["target_file"].replace('.py', '').replace('/', '.').replace('\\', '.')

                import_stmt = f"from {import_path} import execute as {var_name}"
                mapping = f'            "{cap_id}": {var_name},'

                if import_stmt not in content:
                    content = import_stmt + "\n" + content
                if mapping not in content:
                    content = content.replace("self.registry = {", f"self.registry = {{\n{mapping}")

                container_path.write_text(content, encoding='utf-8')
                entry["integration"]["in_container"] = True

    def _update_metrics(self):
        """Calcula o status da cristalização baseado no registro atual."""
        registry = self.master_crystal.get("registry", [])
        total = len(registry)
        
        # Um item está cristalizado se está presente no disco E registrado no container
        crystallized = sum(1 for e in registry if e["integration"]["physically_present"] and e["integration"]["in_container"])
        orphan = total - crystallized

        self.master_crystal["last_scan"] = datetime.now().isoformat()
        self.master_crystal["crystallization_summary"] = {
            "total_capabilities": total,
            "crystallized": crystallized,
            "connected_legacy": 1, # Ajustar conforme necessidade de legado
            "orphan": orphan
        }

    def _save_crystal(self):
        with open(self.paths["crystal"], 'w', encoding='utf-8') as f:
            json.dump(self.master_crystal, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    CrystallizerEngine().run_full_cycle()
