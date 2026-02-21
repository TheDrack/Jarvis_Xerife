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
        self.master_crystal = self._load_json(self.paths["crystal"]) or self._init_crystal()
        
        caps_data = self._load_json(self.paths["caps"])
        self.source_capabilities = caps_data.get('capabilities', []) if caps_data else []

    def _load_json(self, path: Path):
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def _init_crystal(self):
        return {
            "system_id": "JARVIS_CORE",
            "version": "2.5.0",
            "last_scan": datetime.now().isoformat(),
            "crystallization_summary": {
                "total_capabilities": 0,
                "crystallized": 0,
                "orphan": 0
            },
            "registry": []
        }

    def _map_target(self, cap: Dict[str, Any]) -> str:
        title = cap.get('title', '').lower()
        if any(x in title for x in ["inventory", "gap", "objective"]): return "app/domain/gears/"
        if any(x in title for x in ["classify", "model", "entity"]): return "app/domain/models/"
        return "app/domain/capabilities/"

    def run_full_cycle(self):
        logger.info("🧠 Mapeando Redes Neurais e Dependências...")
        self.audit_and_link()
        self.transmute()
        self.stitch_sectors()
        self._update_metrics()
        self._save_crystal()
        logger.info("✨ Redes sincronizadas e cristalizadas.")

    def audit_and_link(self):
        """Documenta capacidades e mapeia a árvore de dependências."""
        new_registry = []
        for cap in self.source_capabilities:
            cap_id = cap['id']
            target_dir = self._map_target(cap)
            target_file = f"{cap_id.lower().replace('-', '_')}_core.py"
            target_path = os.path.join(target_dir, target_file)
            sector = "gears" if "gears" in target_path else \
                     "models" if "models" in target_path else \
                     "adapters" if "adapters" in target_path else "capabilities"

            container_file = self.sectors[sector]
            in_container = False
            if container_file.exists():
                in_container = f'"{cap_id}"' in container_file.read_text(encoding='utf-8')

            # Inclusão vital do 'depends_on' para o Hub
            new_registry.append({
                "id": cap_id,
                "title": cap.get('title'),
                "status": cap.get('status', 'nonexistent'),
                "depends_on": cap.get('depends_on', []), # Mapeamento de dependência
                "sector": sector,
                "genealogy": {"target_file": target_path},
                "integration": {
                    "in_container": in_container,
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
                    f"'''CAPABILITY: {entry['title']}\n"
                    f"DEPENDS ON: {entry['depends_on']}'''\n"
                    "def execute(context=None):\n"
                    f"    return {{'status': 'active', 'id': '{entry['id']}'}}\n"
                )
                t_path.write_text(content, encoding='utf-8')
                entry["integration"]["physically_present"] = True

    def stitch_sectors(self):
        for entry in self.master_crystal["registry"]:
            if entry["integration"]["physically_present"] and not entry["integration"]["in_container"]:
                sector = entry["sector"]
                container_path = self.sectors[sector]
                
                if not container_path.exists():
                    container_path.write_text(f"# -*- coding: utf-8 -*-\nclass {sector.capitalize()}Container:\n    def __init__(self):\n        self.registry = {{}}\n", encoding='utf-8')

                content = container_path.read_text(encoding='utf-8')
                cap_id = entry["id"]
                var_name = f"{cap_id.lower().replace('-', '_')}_exec"
                import_path = entry["genealogy"]["target_file"].replace('.py', '').replace('/', '.').replace('\\', '.')

                if f"from {import_path}" not in content:
                    content = f"from {import_path} import execute as {var_name}\n" + content
                if f'"{cap_id}":' not in content:
                    content = content.replace("self.registry = {", f"self.registry = {{\n            \"{cap_id}\": {var_name},")

                container_path.write_text(content, encoding='utf-8')
                entry["integration"]["in_container"] = True

    def _update_metrics(self):
        """Conta apenas capacidades 'complete' que possuem arquivos e estão no container."""
        reg = self.master_crystal["registry"]
        # Filtragem rigorosa por status 'complete'
        crystallized = sum(1 for e in reg if e["status"] == "complete" and e["integration"]["in_container"])
        
        self.master_crystal["crystallization_summary"] = {
            "total_capabilities": len(reg),
            "crystallized": crystallized,
            "orphan": len(reg) - crystallized
        }

    def _save_crystal(self):
        with open(self.paths["crystal"], 'w', encoding='utf-8') as f:
            json.dump(self.master_crystal, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    CrystallizerEngine().run_full_cycle()
