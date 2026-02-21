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

        self.paths["container_dir"].mkdir(parents=True, exist_ok=True)
        self.master_crystal = self._load_json(self.paths["crystal"]) or self._init_crystal()
        
        caps_data = self._load_json(self.paths["caps"])
        self.source_capabilities = caps_data.get('capabilities', []) if caps_data else []

    def _load_json(self, path: Path):
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def _extract_libraries(self, file_path: Path) -> List[str]:
        """Auto-Sensing: Extrai bibliotecas raiz dos ficheiros .py"""
        if not file_path.exists():
            return []
        
        libs = set()
        try:
            content = file_path.read_text(encoding='utf-8')
            patterns = [
                r'^\s*import\s+([a-zA-Z0-9_]+)',
                r'^\s*from\s+([a-zA-Z0-9_]+)'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                for lib in matches:
                    ignored = ['app', 'hub', 'json', 're', 'os', 'sys', 'pathlib', 'typing', 'datetime', 'logging', 'abc']
                    if lib not in ignored:
                        libs.add(lib)
        except Exception as e:
            logger.error(f"❌ Erro no scan de {file_path.name}: {e}")
        
        return sorted(list(libs))

    def audit_and_link(self):
        """Mapeia o DNA e documenta bibliotecas detetadas."""
        new_registry = []
        for cap in self.source_capabilities:
            cap_id = cap['id']
            target_dir = self._map_target(cap)
            target_file_name = f"{cap_id.lower().replace('-', '_')}_core.py"
            target_path = Path(target_dir) / target_file_name
            
            sector = "gears" if "gears" in str(target_path) else \
                     "models" if "models" in str(target_path) else \
                     "adapters" if "adapters" in str(target_path) else "capabilities"

            detected_libs = self._extract_libraries(target_path)

            new_registry.append({
                "id": cap_id,
                "title": cap.get('title'),
                "status": cap.get('status', 'nonexistent'),
                "mapped_libraries": detected_libs,
                "sector": sector,
                "genealogy": {"target_file": str(target_path)},
                "integration": {
                    "in_container": self._check_container(cap_id, sector),
                    "physically_present": target_path.exists()
                }
            })
        self.master_crystal["registry"] = new_registry

    def transmute(self):
        """Garante a infraestrutura física das capacidades."""
        for cap in self.source_capabilities:
            target_dir = Path(self._map_target(cap))
            target_file = f"{cap['id'].lower().replace('-', '_')}_core.py"
            target_path = target_dir / target_file
            
            if not target_path.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                content = ("# -*- coding: utf-8 -*-\ndef execute(context=None):\n"
                           f"    return {{'status': 'active', 'id': '{cap['id']}'}}\n")
                target_path.write_text(content, encoding='utf-8')

    def stitch_sectors(self):
        """Vincula as capacidades aos containers Python."""
        for entry in self.master_crystal["registry"]:
            if entry["integration"]["physically_present"] and not entry["integration"]["in_container"]:
                sector = entry["sector"]
                container_path = self.sectors[sector]

                if not container_path.exists():
                    container_path.write_text("# -*- coding: utf-8 -*-\nclass Container:\n    def __init__(self):\n        self.registry = {}\n", encoding='utf-8')

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

    def _map_target(self, cap: Dict[str, Any]) -> str:
        title = cap.get('title', '').lower()
        if any(x in title for x in ["inventory", "gap", "objective", "neural"]): return "app/domain/gears/"
        if any(x in title for x in ["classify", "model", "entity"]): return "app/domain/models/"
        return "app/domain/capabilities/"

    def _check_container(self, cap_id: str, sector: str) -> bool:
        container_file = self.sectors.get(sector)
        return cap_id in container_file.read_text() if container_file and container_file.exists() else False

    def _save_crystal(self):
        self.master_crystal["last_scan"] = datetime.now().isoformat()
        with open(self.paths["crystal"], 'w', encoding='utf-8') as f:
            json.dump(self.master_crystal, f, indent=4, ensure_ascii=False)

    def _init_crystal(self):
        return {"system_id": "JARVIS_CORE", "version": "2.8.5", "registry": []}

    def run_full_cycle(self):
        self.transmute()
        self.audit_and_link()
        self.stitch_sectors()
        self._save_crystal()

if __name__ == "__main__":
    CrystallizerEngine().run_full_cycle()
