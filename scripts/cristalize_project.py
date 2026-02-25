import os
import logging
import py_compile
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

# =========================
# Configuração JARVIS
# =========================
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("JARVIS_Crystallizer_V5_6")

DRY_RUN = False 

class ProjectCrystallizer:
    def __init__(self, dry_run: bool = False):
        self.base_path = Path(".").resolve()
        self.dry_run = dry_run
        
        # PROTEÇÃO: Diretórios e arquivos que nunca devem ser alterados
        self.forbidden_dirs = {
            ".git", ".venv", "venv", "__pycache__", 
            "backups", "scripts", ".github", "core"
        }
        self.ignore_files = {
            "__init__.py", "nexus.py", "cristalize_project.py", "nexuscomponent.py"
        }
        
        self.nexus_import = "from app.core.nexuscomponent import NexusComponent"
        self.target_parent = "NexusComponent"

    def _create_checkpoint(self):
        backup_dir = self.base_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = backup_dir / f"checkpoint_{ts}.tar.gz"
        
        with tarfile.open(archive, "w:gz") as tar:
            for f in self.base_path.rglob("*.py"):
                if not any(part in self.forbidden_dirs for part in f.parts):
                    tar.add(f, arcname=str(f.relative_to(self.base_path)))
        logger.info(f"📦 Backup: {archive.name}")

    def _is_blacklisted_structure(self, code: str) -> bool:
        """
        Detecta se a classe é uma estrutura de dados pura que não suporta NexusComponent.
        Resolve o erro de 'metaclass conflict' em Enums e inconsistências em Dataclasses.
        """
        indicators = [
            "(Enum)", "(enum.Enum)", "(str, Enum)", 
            "@dataclass", "BaseModel", "(SQLModel)"
        ]
        return any(ind in code for ind in indicators)

    def _apply_crystal_logic(self, code: str) -> str:
        lines = code.splitlines()
        modified = False
        
        # 1. Verificar se o arquivo contém uma classe válida para cristalização
        if "class " not in code or self._is_blacklisted_structure(code):
            return code

        # 2. Garantir o Import
        if self.nexus_import not in code:
            insert_pos = 0
            for i, line in enumerate(lines):
                if "__future__" in line or "import " in line:
                    insert_pos = i + 1
            lines.insert(insert_pos, self.nexus_import)
            modified = True
            
        # 3. Injeção de Herança e Método Execute
        new_lines = []
        for line in lines:
            stripped = line.strip()
            # Classe sem herança
            if stripped.startswith("class ") and ":" in line and "(" not in line:
                line = line.replace(":", f"({self.target_parent}):")
                modified = True
            # Classe com herança mas sem NexusComponent
            elif stripped.startswith("class ") and "(" in line and self.target_parent not in line:
                # Evita duplicar se já houver parênteses de outra herança
                line = line.replace("(", f"({self.target_parent}, ")
                modified = True
            new_lines.append(line)

        # 4. Adicionar template do método execute se ausente
        if modified and "def execute" not in code:
            new_lines.append("\n    def execute(self, context: dict):")
            new_lines.append("        \"\"\"Execução cristalizada do componente.\"\"\"")
            new_lines.append("        pass")

        return "\n".join(new_lines) if modified else code

    def run(self):
        if not self.dry_run:
            self._create_checkpoint()
            
        logger.info(f"⚡ Ciclo de Cristalização DNA V5.6")
        count = 0
        
        for py_file in self.base_path.rglob("*.py"):
            if any(part in self.forbidden_dirs for part in py_file.parts): continue
            if py_file.name in self.ignore_files: continue
            
            try:
                old_code = py_file.read_text(encoding="utf-8")
                new_code = self._apply_crystal_logic(old_code)
                
                if old_code != new_code:
                    py_file.write_text(new_code, encoding="utf-8")
                    logger.info(f"✨ Cristalizado: {py_file.name}")
                    count += 1
            except Exception as e:
                logger.error(f"🚨 Falha em {py_file.name}: {e}")

        logger.info(f"🏁 Finalizado. {count} arquivos estabilizados.")

if __name__ == "__main__":
    ProjectCrystallizer(dry_run=DRY_RUN).run()
