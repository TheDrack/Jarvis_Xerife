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
        
        # Mapeamento dos arquivos de Container (Onde o Hub busca as referências)
        self.sectors = {
            "gears": self.paths["container_dir"] / "gears_container.py",
            "models": self.paths["container_dir"] / "models_container.py",
            "adapters": self.paths["container_dir"] / "adapters_container.py",
            "capabilities": self.paths["container_dir"] / "capabilities_container.py"
        }

        # Inicialização do Master Crystal
        self.paths["container_dir"].mkdir(parents=True, exist_ok=True)
        self.master_crystal = self._load_json(self.paths["crystal"]) or self._init_crystal()
        
        # Carregamento da fonte de verdade (Inventário)
        caps_data = self._load_json(self.paths["caps"])
        self.source_capabilities = caps_data.get('capabilities', []) if caps_data else []

    def _load_json(self, path: Path):
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def _extract_libraries(self, file_path: Path) -> List[str]:
        """
        Faz o parsing resiliente para encontrar imports reais.
        Varre o arquivo em busca de assinaturas de bibliotecas externas.
        """
        if not file_path.exists():
            logger.warning(f"⚠️ Arquivo não encontrado para scan: {file_path}")
            return []
        
        libs = set()
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # Regex Flexível: Pega imports no início da linha, mesmo com espaços.
            # Captura apenas o nome base da biblioteca (ex: 'pandas' em 'import pandas as pd')
            import_patterns = [
                r'^\s*import\s+([a-zA-Z0-9_]+)',
                r'^\s*from\s+([a-zA-Z0-9_]+)'
            ]
            
            for pattern in import_patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                for lib in matches:
                    # Filtro para ignorar o próprio sistema e bibliotecas core do Python
                    ignored = [
                        'app', 'hub', 'json', 're', 'os', 'sys', 'pathlib', 
                        'typing', 'datetime', 'logging', 'abc', 'time', 'random'
                    ]
                    if lib not in ignored:
                        libs.add(lib)
            
            if libs:
                logger.info(f"🧬 Libs detectadas em {file_path.name}: {list(libs)}")
        except Exception as e:
            logger.error(f"❌ Erro ao escanear {file_path}: {e}")
        
        return sorted(list(libs))

    def _map_target(self, cap: Dict[str, Any]) -> str:
        """Define o diretório de destino baseado no título/função da CAP."""
        title = cap.get('title', '').lower()
        # Regras de Setorização
        if any(x in title for x in ["inventory", "gap", "objective", "neural", "ia", "brain"]): 
            return "app/domain/gears/"
        if any(x in title for x in ["classify", "model", "entity", "state", "schema"]): 
            return "app/domain/models/"
        if any(x in title for x in ["api", "client", "http", "git", "file", "os", "system"]): 
            return "app/domain/adapters/"
        
        return "app/domain/capabilities/"

    def audit_and_link(self):
        """Mapeia o DNA: Cruza o inventário com os arquivos físicos e detecta as libs."""
        new_registry = []
        for cap in self.source_capabilities:
            cap_id = cap['id']
            target_dir = self._map_target(cap)
            target_file_name = f"{cap_id.lower().replace('-', '_')}_core.py"
            target_path = Path(target_dir) / target_file_name
            
            sector = "gears" if "gears" in str(target_path) else \
                     "models" if "models" in str(target_path) else \
                     "adapters" if "adapters" in str(target_path) else "capabilities"

            # O CORAÇÃO DO AUTO-SENSING:
            # Só extrai se o arquivo existir (o run_full_cycle garante isso rodando transmute antes)
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
        """Garante a existência física dos arquivos de capacidade."""
        for cap in self.source_capabilities:
            target_dir = Path(self._map_target(cap))
            target_file = f"{cap['id'].lower().replace('-', '_')}_core.py"
            target_path = target_dir / target_file
            
            if not target_path.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                content = (
                    "# -*- coding: utf-8 -*-\n"
                    f"'''CAPABILITY: {cap.get('title')}'''\n\n"
                    "def execute(context=None):\n"
                    f"    # Template gerado pelo Crystallizer\n"
                    f"    return {{'status': 'active', 'id': '{cap['id']}'}}\n"
                )
                target_path.write_text(content, encoding='utf-8')
                logger.info(f"💠 Arquivo criado: {target_path}")

    def stitch_sectors(self):
        """Realiza a costura (registro) das capacidades nos containers de setor."""
        for entry in self.master_crystal["registry"]:
            if entry["integration"]["physically_present"] and not entry["integration"]["in_container"]:
                sector = entry["sector"]
                container_path = self.sectors[sector]

                # Cria o container se não existir
                if not container_path.exists():
                    container_path.write_text("# -*- coding: utf-8 -*-\nclass Container:\n    def __init__(self):\n        self.registry = {}\n", encoding='utf-8')

                content = container_path.read_text(encoding='utf-8')
                cap_id = entry["id"]
                var_name = f"{cap_id.lower().replace('-', '_')}_exec"
                
                # Prepara o caminho de importação (converte path em módulo python)
                import_path = entry["genealogy"]["target_file"].replace('.py', '').replace('/', '.').replace('\\', '.')
                if import_path.startswith('.'): import_path = import_path[1:]

                # Injeta o Import e o Registro no dicionário do Container
                if f"from {import_path}" not in content:
                    content = f"from {import_path} import execute as {var_name}\n" + content
                
                if f'"{cap_id}":' not in content:
                    # Injeção dinâmica no construtor da classe
                    content = content.replace("self.registry = {", f"self.registry = {{\n            \"{cap_id}\": {var_name},")

                container_path.write_text(content, encoding='utf-8')
                entry["integration"]["in_container"] = True
                logger.info(f"🧵 {cap_id} costurado no setor {sector}")

    def _check_container(self, cap_id: str, sector: str) -> bool:
        container_file = self.sectors.get(sector)
        if container_file and container_file.exists():
            return f'"{cap_id}"' in container_file.read_text(encoding='utf-8')
        return False

    def _update_metrics(self):
        reg = self.master_crystal["registry"]
        crystallized = sum(1 for e in reg if e["status"] == "complete" and e["integration"]["in_container"])
        self.master_crystal["crystallization_summary"] = {
            "total_capabilities": len(reg),
            "crystallized": crystallized,
            "orphan": len(reg) - crystallized
        }

    def _save_crystal(self):
        self.master_crystal["last_scan"] = datetime.now().isoformat()
        with open(self.paths["crystal"], 'w', encoding='utf-8') as f:
            json.dump(self.master_crystal, f, indent=4, ensure_ascii=False)
        logger.info(f"💾 Master Crystal salvo com {len(self.master_crystal['registry'])} entradas.")

    def _init_crystal(self):
        return {
            "system_id": "JARVIS_CORE",
            "version": "2.7.5",
            "registry": []
        }

    def run_full_cycle(self):
        """Executa o ciclo completo de sincronização do ecossistema."""
        logger.info("📡 Iniciando Full Cycle de Cristalização...")
        
        # 1. Primeiro garante que os arquivos físicos existem
        self.transmute()
        
        # 2. Depois faz a auditoria (Scan de Bibliotecas funciona aqui porque os arquivos já existem)
        self.audit_and_link()
        
        # 3. Registra tudo nos containers Python para o Hub
        self.stitch_sectors()
        
        # 4. Atualiza os metadados finais
        self._update_metrics()
        
        # 5. Persiste o mapa no Master Crystal
        self._save_crystal()
        
        logger.info("✨ Sistema Sincronizado.")

if __name__ == "__main__":
    CrystallizerEngine().run_full_cycle()
