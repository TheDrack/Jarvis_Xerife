import os
import logging
import py_compile
import tarfile
import re
from datetime import datetime
from pathlib import Path

# =========================
# Configuração JARVIS
# =========================
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("JARVIS_Crystallizer_V5_7")

DRY_RUN = False 

class ProjectCrystallizer:
    def __init__(self, dry_run: bool = False):
        self.base_path = Path(".").resolve()
        self.dry_run = dry_run

        # PROTEÇÃO: Diretórios e arquivos base
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

    def _is_blacklisted(self, code: str) -> bool:
        """Evita conflitos de metaclasses e corrupção de modelos."""
        blacklist = ["(Enum)", "(enum.Enum)", "(str, Enum)", "@dataclass", "BaseModel", "(SQLModel)"]
        return any(item in code for item in blacklist)

    def _apply_crystal_logic(self, code: str) -> str:
        # 1. Se não houver classes ou for blacklist, retornar original
        if "class " not in code or self._is_blacklisted(code):
            return code

        new_code = code

        # 2. Injeção de Import (apenas se não existir)
        if self.target_parent not in code:
            # Insere no topo, mas após docstrings se existirem
            import_block = f"{self.nexus_import}\n"
            if code.startswith('"""') or code.startswith("'''"):
                end_doc = code.find('"""', 3) if code.startswith('"""') else code.find("'''", 3)
                if end_doc != -1:
                    new_code = code[:end_doc+3] + "\n" + import_block + code[end_doc+3:]
            else:
                new_code = import_block + code

        # 3. Injeção de Herança via Regex (Apenas no início da linha para evitar métodos internos)
        # Transforma: class Nome:  -> class Nome(NexusComponent):
        new_code = re.sub(r'^class\s+(\w+)\s*:', rf'class \1({self.target_parent}):', new_code, flags=re.MULTILINE)

        # Transforma: class Nome(Base): -> class Nome(NexusComponent, Base):
        # Evita duplicar se NexusComponent já estiver lá
        new_code = re.sub(rf'^class\s+(\w+)\s*\((?!.*{self.target_parent})', rf'class \1({self.target_parent}, ', new_code, flags=re.MULTILINE)

        # 4. Injeção do método execute se a classe foi alterada e ele não existe
        if self.target_parent in new_code and "def execute" not in new_code:
            # Encontra o final do bloco da classe para inserir
            new_code = re.sub(r'^(class\s+.*:)$', r'\1\n\n    def execute(self, context: dict):\n        pass', new_code, flags=re.MULTILINE)

        return new_code

    def run(self):
        if not self.dry_run:
            self._create_checkpoint()

        logger.info(f"⚡ Protocolo JARVIS V5.7 | Estabilização de Sintaxe")
        count = 0

        for py_file in self.base_path.rglob("*.py"):
            if any(part in self.forbidden_dirs for part in py_file.parts): continue
            if py_file.name in self.ignore_files: continue

            try:
                old_code = py_file.read_text(encoding="utf-8")
                new_code = self._apply_crystal_logic(old_code)

                if old_code != new_code:
                    # Validação pré-escrita
                    try:
                        compile(new_code, py_file.name, 'exec')
                        py_file.write_text(new_code, encoding="utf-8")
                        logger.info(f"✨ Cristalizado: {py_file.name}")
                        count += 1
                    except SyntaxError as e:
                        logger.error(f"❌ Abortado: Erro de sintaxe gerado em {py_file.name}: {e}")
            except Exception as e:
                logger.error(f"🚨 Falha crítica em {py_file.name}: {e}")

        logger.info(f"🏁 Finalizado. {count} arquivos operacionais.")

if __name__ == "__main__":
    ProjectCrystallizer(dry_run=DRY_RUN).run()
