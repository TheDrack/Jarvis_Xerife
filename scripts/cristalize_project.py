import os
import logging
import py_compile
import tarfile
import re
import tempfile
from datetime import datetime
from pathlib import Path

# =========================
# Configuração JARVIS
# =========================
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("JARVIS_Crystallizer_V5_8")

DRY_RUN = False 

class ProjectCrystallizer:
    def __init__(self, dry_run: bool = False):
        self.base_path = Path(".").resolve()
        self.dry_run = dry_run

        # PROTEÇÃO: Diretórios que o sistema NUNCA deve tentar cristalizar
        self.forbidden_dirs = {
            ".git", ".venv", "venv", "__pycache__", 
            "backups", "scripts", ".github", "core",
            "crystallization"  # PROTEÇÃO CRÍTICA: Impede de quebrar o próprio motor
        }

        # Arquivos específicos ignorados
        self.ignore_files = {
            "__init__.py", "nexus.py", "cristalize_project.py", 
            "nexuscomponent.py", "crystallizer_engine.py"
        }

        from app.core.nexus import NexusComponent
        self.target_parent = "NexusComponent"

    def _create_checkpoint(self):
        """Gera backup tar.gz antes da execução."""
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
        """Filtra classes que não suportam a herança NexusComponent por conflitos de tipo."""
        blacklist = [
            "(Enum)", "(enum.Enum)", "(str, Enum)", 
            "@dataclass", "BaseModel", "(SQLModel)",
            "class CrystallizerEngine" # Blindagem extra via código
        ]
        return any(item in code for item in blacklist)

    def _apply_crystal_logic(self, code: str) -> str:
        """Aplica as regras de cristalização DNA."""
        if "class " not in code or self._is_blacklisted(code):
            return code

        new_code = code

        # 1. Injeção de Import no escopo global (evita SyntaxError dentro de métodos)
        if self.target_parent not in code:
            import_block = f"{self.nexus_import}\n"
            # Se tiver docstring, insere depois dela. Se não, no topo.
            if code.startswith('"""') or code.startswith("'''"):
                doc_pattern = r'^("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')'
                match = re.match(doc_pattern, code)
                if match:
                    end_pos = match.end()
                    new_code = code[:end_pos] + "\n" + import_block + code[end_pos:]
            else:
                new_code = import_block + code

        # 2. Injeção de Herança (Apenas no início da linha para segurança total)
        # Caso A: class Nome:
        new_code = re.sub(r'^class\s+(\w+)\s*:', rf'class \1({self.target_parent}):', new_code, flags=re.MULTILINE)

        # Caso B: class Nome(Outra): -> class Nome(NexusComponent, Outra):
        # Negative lookahead garante que não duplicamos a herança
        new_code = re.sub(rf'^class\s+(\w+)\s*\((?!.*{self.target_parent})', rf'class \1({self.target_parent}, ', new_code, flags=re.MULTILINE)

        # 3. Injeção do método execute (se a classe agora é NexusComponent mas está vazia)
        if self.target_parent in new_code and "def execute" not in new_code:
            # Encontra a declaração da classe e insere o método logo abaixo
            new_code = re.sub(
                r'^(class\s+.*:)$', 
                r'\1\n\n    def execute(self, context: dict):\n        """Execução automática JARVIS."""\n        pass', 
                new_code, 
                flags=re.MULTILINE
            )

        return new_code

    def run(self):
        if not self.dry_run:
            self._create_checkpoint()

        logger.info(f"⚡ Protocolo JARVIS V5.8 | Estabilização DNA")
        count = 0

        for py_file in self.base_path.rglob("*.py"):
            # Filtro de diretórios e arquivos
            if any(part in self.forbidden_dirs for part in py_file.parts): continue
            if py_file.name in self.ignore_files: continue

            try:
                old_code = py_file.read_text(encoding="utf-8")
                new_code = self._apply_crystal_logic(old_code)

                if old_code != new_code:
                    # Teste de integridade antes de salvar
                    try:
                        compile(new_code, py_file.name, 'exec')
                        py_file.write_text(new_code, encoding="utf-8")
                        logger.info(f"✨ Cristalizado: {py_file.name}")
                        count += 1
                    except SyntaxError as e:
                        logger.error(f"❌ Abortado: {py_file.name} falhou no teste de sintaxe: {e}")
            except Exception as e:
                logger.error(f"🚨 Falha crítica em {py_file.name}: {e}")

        logger.info(f"🏁 Finalizado. {count} arquivos estabilizados.")

if __name__ == "__main__":
    ProjectCrystallizer(dry_run=DRY_RUN).run()
