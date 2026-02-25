import os
import shutil
import logging
import py_compile
import tarfile
from datetime import datetime
from pathlib import Path

# =========================
# Configuração JARVIS
# =========================
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("JARVIS_Crystallizer_V5_5_Final")

# Defina como False para aplicar as mudanças automaticamente
DRY_RUN = False 

class ProjectCrystallizer:
    def __init__(self, dry_run: bool = False):
        self.base_path = Path(".").resolve()
        self.dry_run = dry_run

        # PROTEÇÃO: Pastas que o cristalizador não deve tocar
        self.forbidden_dirs = {
            ".git", ".venv", "venv", "__pycache__", 
            "backups", "scripts", ".github", "core"
        }

        # Arquivos específicos para ignorar
        self.ignore_files = {
            "__init__.py", "nexus.py", "cristalize_project.py",
            "nexuscomponent.py" # Proteção extra para o arquivo base
        }

        self.nexus_import = "from app.core.nexuscomponent import NexusComponent"
        self.target_parent = "NexusComponent"

    def _create_checkpoint(self):
        """Gera backup comprimido antes de qualquer alteração."""
        backup_dir = self.base_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = backup_dir / f"checkpoint_{ts}.tar.gz"

        with tarfile.open(archive, "w:gz") as tar:
            for f in self.base_path.rglob("*.py"):
                if not any(part in self.forbidden_dirs for part in f.parts):
                    tar.add(f, arcname=str(f.relative_to(self.base_path)))
        logger.info(f"📦 Backup de segurança gerado: {archive.name}")

    def _should_process(self, file_path: Path, code: str) -> bool:
        """Filtra se o arquivo deve ser cristalizado."""
        # Não processar se não houver definição de classe
        if "class " not in code:
            return False

        # Ignorar DataStructures puras (Dataclasses e Enums)
        # Isso evita injetar NexusComponent em modelos de dados simples
        if "@dataclass" in code or "(Enum)" in code or "(enum.Enum)" in code:
            return False

        return True

    def _apply_crystal_logic(self, code: str) -> str:
        """Aplica as transformações estruturais via manipulação de texto segura."""
        lines = code.splitlines()
        modified = False

        # 1. Garantir o Import do NexusComponent
        if "from app.core.nexuscomponent import NexusComponent" not in code:
            # Insere após o __future__ ou no topo
            insert_pos = 0
            for i, line in enumerate(lines):
                if "__future__" in line:
                    insert_pos = i + 1
            lines.insert(insert_pos, self.nexus_import)
            modified = True

        # 2. Garantir Herança e Método Execute
        new_lines = []
        for line in lines:
            # Identifica definição de classe sem herança: class MyClass:
            if line.strip().startswith("class ") and ":" in line and "(" not in line:
                line = line.replace(":", f"({self.target_parent}):")
                modified = True
            # Identifica definição de classe com outra herança: class MyClass(Base):
            elif line.strip().startswith("class ") and "(" in line and self.target_parent not in line:
                line = line.replace("(", f"({self.target_parent}, ")
                modified = True
            new_lines.append(line)

        # 3. Adicionar método execute se a classe não tiver
        # (Lógica simplificada: adiciona se houver uma classe e nenhum def execute)
        if "def execute" not in code and modified:
            new_lines.append("\n    def execute(self, context: dict):")
            new_lines.append("        pass")

        return "\n".join(new_lines) if modified else code

    def _validate_syntax(self, content: str, original_path: Path) -> bool:
        """Valida se a transformação não quebrou o Python."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
            tmp.write(content.encode('utf-8'))
            tmp_path = tmp.name
        try:
            py_compile.compile(tmp_path, doraise=True)
            return True
        except Exception as e:
            logger.error(f"❌ Falha de sintaxe gerada para {original_path.name}: {e}")
            return False
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def run(self):
        if not self.dry_run:
            self._create_checkpoint()

        logger.info(f"⚡ Iniciando Cristalização DNA V5.5 [Modo: {'DRY' if self.dry_run else 'LIVE'}]")
        count = 0

        for py_file in self.base_path.rglob("*.py"):
            # Filtros de exclusão
            if any(part in self.forbidden_dirs for part in py_file.parts): continue
            if py_file.name in self.ignore_files: continue

            try:
                old_code = py_file.read_text(encoding="utf-8")

                if not self._should_process(py_file, old_code):
                    continue

                new_code = self._apply_crystal_logic(old_code)

                if old_code != new_code:
                    if self.dry_run:
                        logger.info(f"🔍 [DRY-RUN] Alteração detectada em: {py_file.name}")
                        count += 1
                    else:
                        py_file.write_text(new_code, encoding="utf-8")
                        logger.info(f"✨ Cristalizado: {py_file.name}")
                        count += 1
            except Exception as e:
                logger.error(f"🚨 Erro fatal em {py_file.name}: {e}")

        logger.info(f"🏁 Protocolo concluído. {count} componentes sincronizados com o Nexus.")

import tempfile
if __name__ == "__main__":
    ProjectCrystallizer(dry_run=DRY_RUN).run()
