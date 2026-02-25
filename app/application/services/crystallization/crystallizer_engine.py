# -*- coding: utf-8 -*-
import json
import os
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Configuração de Log JARVIS
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Crystallizer")

class CrystallizerEngine:
    def __init__(self, cap_path="data/capabilities.json", crystal_path="data/master_crystal.json"):
        # Foco em dados e setores do domínio
        self.paths = {
            "caps": Path(cap_path),
            "crystal": Path(crystal_path),
            "app_dir": Path("app")
        }

        # Inicialização do Crystal (Bússola do Sistema)
        self.master_crystal = self._load_json(self.paths["crystal"]) or self._init_crystal()

        # Carregamento das intenções/capacidades
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

    def _extract_libraries(self, file_path: Path) -> List[str]:
        """Auto-Sensing: Extrai bibliotecas raiz para o DNA do Crystal."""
        if not file_path.exists():
            return []
        libs = set()
        try:
            content = file_path.read_text(encoding='utf-8')
            # Regex robusta para imports globais
            patterns = [r'^\s*import\s+([a-zA-Z0-9_]+)', r'^\s*from\s+([a-zA-Z0-9_]+)']
            for pattern in patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                for lib in matches:
                    ignored = ['app', 'json', 're', 'os', 'sys', 'pathlib', 'typing', 'datetime', 'logging', 'abc']
                    if lib not in ignored:
                        libs.add(lib)
        except Exception as e:
            logger.error(f"❌ Erro no scan de {file_path.name}: {e}")
        return sorted(list(libs))

    def audit_and_link(self):
        """Mapeia o DNA e atualiza o Registro do Master Crystal para o Nexus."""
        new_registry = []
        for cap in self.source_capabilities:
            cap_id = cap['id']
            target_dir = self._map_target(cap)
            target_file_name = f"{cap_id.lower().replace('-', '_')}.py"
            target_path = Path(target_dir) / target_file_name

            sector = "domain/gears" if "gears" in str(target_path) else \
                     "domain/models" if "models" in str(target_path) else "domain/capabilities"

            detected_libs = self._extract_libraries(target_path)

            new_registry.append({
                "id": cap_id,
                "title": cap.get('title'),
                "status": "active" if target_path.exists() else "pending",
                "mapped_libraries": detected_libs,
                "nexus_hint": sector,
                "path": str(target_path).replace("\\", "/"),
                "last_audit": datetime.now().isoformat()
            })
        self.master_crystal["registry"] = new_registry

    def transmute(self):
        """Garante a existência física seguindo o padrão NexusComponent."""
        for cap in self.source_capabilities:
            target_dir = Path(self._map_target(cap))
            target_file = f"{cap['id'].lower().replace('-', '_')}.py"
            target_path = target_dir / target_file

            if not target_path.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                # Formata o nome da classe (ex: neural_network -> NeuralNetwork)
                class_name = "".join(word.capitalize() for word in cap['id'].replace('-', '_').split("_"))

                content = (
                    "# -*- coding: utf-8 -*-\n"
                    "from app.core.nexuscomponent import NexusComponent\n\n"
                    f"class {class_name}(NexusComponent):\n"
                    "    \"\"\"\n"
                    f"    Capacidade: {cap.get('title')}\n"
                    "    Gerado automaticamente pelo CrystallizerEngine\n"
                    "    \"\"\"\n"
                    "    def execute(self, context: dict = None):\n"
                    f"        return {{'status': 'active', 'id': '{cap['id']}'}}\n"
                )
                target_path.write_text(content, encoding='utf-8')
                logger.info(f"💎 Cristalizado: {target_file}")

    def _map_target(self, cap: Dict[str, Any]) -> str:
        """Mapeia o setor de destino no domínio."""
        title = cap.get('title', '').lower()
        if any(x in title for x in ["inventory", "gap", "objective", "neural"]): return "app/domain/gears"
        if any(x in title for x in ["classify", "model", "entity"]): return "app/domain/models"
        return "app/domain/capabilities"

    def _save_crystal(self):
        """Persiste o Master Crystal."""
        self.master_crystal["last_scan"] = datetime.now().isoformat()
        self.paths["crystal"].parent.mkdir(parents=True, exist_ok=True)
        with open(self.paths["crystal"], 'w', encoding='utf-8') as f:
            json.dump(self.master_crystal, f, indent=4, ensure_ascii=False)
        logger.info(f"🔮 Master Crystal atualizado: {self.paths['crystal']}")

    def _init_crystal(self):
        return {"system_id": "JARVIS_CORE", "version": "3.1.0 (Nexus Stable)", "registry": []}

    def run_full_cycle(self):
        """Ciclo completo de vida sem dependências obsoletas."""
        logger.info("🚀 Iniciando Ciclo de Cristalização Nexus V3.1...")
        self.transmute()
        self.audit_and_link()
        self._save_crystal()
        logger.info("✅ Ciclo completo. O Nexus está operacional.")

if __name__ == "__main__":
    CrystallizerEngine().run_full_cycle()
