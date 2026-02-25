import os
import shutil
import logging
import difflib
import tempfile
import py_compile
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Set, List

import libcst as cst
from libcst.metadata import ScopeProvider, QualifiedNameProvider, FunctionScope

# =========================
# Configuração JARVIS
# =========================
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("JARVIS_Crystallizer_V5_4")

DRY_RUN = False 

# =========================
# Transformers e Filtros
# =========================
class NexusExecuteTransformer(cst.CSTTransformer):
    def __init__(self, target_parent: str):
        self.target_parent = target_parent

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef):
        # FILTRO DE DNA: Não cristalizar Enums ou Dataclasses puras
        decorators = [str(d.decorator.value if hasattr(d.decorator, "value") else "") for d in updated_node.decorators]
        is_data_structure = any(d in ["dataclass", "enum.Enum", "Enum"] for d in decorators)

        if is_data_structure:
            return updated_node

        bases = list(updated_node.bases)
        is_already_child = any(
            (isinstance(b.value, cst.Name) and b.value.value == self.target_parent)
            for b in bases
        )

        if not is_already_child:
            bases.insert(0, cst.Arg(value=cst.Name(self.target_parent)))

        body = list(updated_node.body.body)
        if not any(isinstance(b, cst.FunctionDef) and b.name.value == "execute" for b in body):
            execute_meth = cst.FunctionDef(
                name=cst.Name("execute"),
                params=cst.Parameters(params=[
                    cst.Param(name=cst.Name("self")),
                    cst.Param(name=cst.Name("context"), annotation=cst.Annotation(cst.Name("dict"))),
                ]),
                body=cst.IndentedBlock(body=[cst.SimpleStatementLine([cst.Pass()])]),
            )
            body.append(execute_meth)

        return updated_node.with_changes(bases=tuple(bases), body=updated_node.body.with_changes(body=tuple(body)))

# =========================
# Engine Principal
# =========================
class ProjectCrystallizer:
    def __init__(self, dry_run: bool = True):
        self.base_path = Path(".").resolve()
        self.dry_run = dry_run
        self.forbidden_dirs = {".git", ".venv", "venv", "__pycache__", "backups", "scripts", ".github"}
        self.ignore_files = {"__init__.py", "nexus.py"}
        self.nexus_import = "from app.core.nexuscomponent import NexusComponent"

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

    def _should_process(self, code: str) -> bool:
        """Verifica se o arquivo contém lógica que merece ser um NexusComponent."""
        # Não processar se for apenas definição de constantes ou tipos
        if "class " not in code: return False
        if "def " not in code and "@dataclass" in code: return False
        return True

    def _fix_file(self, file_path: Path) -> bool:
        try:
            old_code = file_path.read_text(encoding="utf-8")
            if not self._should_process(old_code): return False

            module = cst.parse_module(old_code)

            # Inserir import se não houver
            if "NexusComponent" not in old_code:
                # Lógica simples de inserção no topo
                lines = old_code.splitlines()
                lines.insert(0, self.nexus_import)
                module = cst.parse_module("\n".join(lines))

            # Aplicar Transformação de Classe
            transformer = NexusExecuteTransformer("NexusComponent")
            new_tree = module.visit(transformer)

            new_code = new_tree.code
            if old_code == new_code: return False

            if self.dry_run:
                logger.info(f"🔍 Proposta para {file_path.name}")
                return True

            file_path.write_text(new_code, encoding="utf-8")
            logger.info(f"✨ Cristalizado: {file_path.name}")
            return True
        except Exception as e:
            logger.error(f"🚨 Erro em {file_path.name}: {e}")
            return False

    def crystallize(self):
        if not self.dry_run: self._create_checkpoint()
        count = 0
        for py_file in self.base_path.rglob("*.py"):
            if any(part in self.forbidden_dirs for part in py_file.parts): continue
            if py_file.name in self.ignore_files: continue
            if self._fix_file(py_file): count += 1
        logger.info(f"🏁 Finalizado. {count} arquivos alterados.")

if __name__ == "__main__":
    ProjectCrystallizer(dry_run=DRY_RUN).crystallize()
