import os
import shutil
import logging
import difflib
import tempfile
import py_compile
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Set, List, Optional

import libcst as cst
from libcst.metadata import (
    ScopeProvider, 
    QualifiedNameProvider, 
    GlobalScope, 
    FunctionScope
)

# =========================
# Configuração JARVIS
# =========================
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("JARVIS_Crystallizer_V5_2_Refined")

# IMPORTANTE: No CI/CD, se quiser aplicar as mudanças, mude para False
DRY_RUN = False 

# =========================
# Utils de Estrutura
# =========================
def has_nexus_import(module: cst.Module) -> bool:
    """Verifica se o componente Nexus já está importado."""
    for stmt in module.body:
        if isinstance(stmt, cst.SimpleStatementLine):
            for item in stmt.body:
                code = ""
                if hasattr(item, "module"): # ImportFrom
                    code = str(item.module.value if hasattr(item.module, "value") else "")
                elif hasattr(item, "names"): # Import
                    code = str(item.names[0].name.value if hasattr(item.names[0].name, "value") else "")
                
                if "nexuscomponent" in code.lower() or "nexus" in code.lower():
                    return True
    return False

def insert_import_safely(module: cst.Module, import_stmt: str) -> cst.Module:
    """Insere o import respeitando docstrings e __future__."""
    body = list(module.body)
    insert_at = 0
    
    if body and isinstance(body[0], cst.SimpleStatementLine):
        first = body[0].body[0]
        if isinstance(first, cst.Expr) and isinstance(first.value, (cst.SimpleString, cst.ConcatenatedString)):
            insert_at = 1
            
    while insert_at < len(body):
        stmt = body[insert_at]
        if isinstance(stmt, cst.SimpleStatementLine):
            if any(isinstance(el, cst.ImportFrom) and el.module and getattr(el.module, "value", "") == "__future__" 
                   for el in stmt.body):
                insert_at += 1
                continue
        break
        
    body.insert(insert_at, cst.parse_statement(import_stmt))
    return module.with_changes(body=body)

# =========================
# Transformers Melhorados
# =========================
class NexusExecuteTransformer(cst.CSTTransformer):
    def __init__(self, target_parent: str):
        self.target_parent = target_parent

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef):
        bases = list(updated_node.bases)
        is_already_child = any(
            (isinstance(b.value, cst.Name) and b.value.value == self.target_parent) or
            (isinstance(b.value, cst.Attribute) and getattr(b.value.attr, "value", "") == self.target_parent)
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

class GlobalToContextTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (ScopeProvider, QualifiedNameProvider)

    def __init__(self, global_names: Set[str]):
        self.global_names = global_names
        self.local_defs_stack: List[Set[str]] = []

    def visit_FunctionDef(self, node: cst.FunctionDef):
        self.local_defs_stack.append({p.name.value for p in node.params.params if isinstance(p.name, cst.Name)})

    def leave_FunctionDef(self, node: cst.FunctionDef):
        if self.local_defs_stack: self.local_defs_stack.pop()

    def _is_shadowed(self, name: str) -> bool:
        return any(name in scope for scope in self.local_defs_stack)

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name):
        try:
            scope = self.get_metadata(ScopeProvider, original_node)
        except Exception:
            return updated_node

        if (original_node.value in self.global_names and 
            isinstance(scope, FunctionScope) and 
            not self._is_shadowed(original_node.value)):
            return cst.Call(
                func=cst.Attribute(value=cst.Name("context"), attr=cst.Name("get")),
                args=[cst.Arg(cst.SimpleString(f"'{original_node.value}'"))],
            )
        return updated_node

# =========================
# Engine Principal
# =========================
class ProjectCrystallizer:
    def __init__(self, dry_run: bool = True):
        self.base_path = Path(".").resolve()
        self.dry_run = dry_run
        self.forbidden_dirs = {"core", "infrastructure", ".git", ".venv", "venv", "__pycache__", "backups", "scripts"}
        self.ignore_files = {"__init__.py", "nexus.py", "crystallizer.py", "cristalize_project.py"}
        self.nexus_import = "from app.core.nexuscomponent import NexusComponent"
        self.target_parent = "NexusComponent"

    def _create_checkpoint(self):
        backup_dir = self.base_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = backup_dir / f"checkpoint_{ts}.tar.gz"
        logger.info(f"📦 Backup de segurança gerado: {archive.name}")
        with tarfile.open(archive, "w:gz") as tar:
            for f in self.base_path.rglob("*.py"):
                if not any(part in self.forbidden_dirs for part in f.parts):
                    tar.add(f, arcname=f.relative_to(self.base_path))

    def _validate_syntax(self, path: Path) -> bool:
        try:
            py_compile.compile(str(path), doraise=True)
            return True
        except Exception as e:
            logger.warning(f"⚠️ Erro de sintaxe em {path}: {e}")
            return False

    def _collect_globals(self, module: cst.Module) -> Set[str]:
        names, top_defs = set(), set()
        for node in module.body:
            if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
                top_defs.add(node.name.value)
            elif isinstance(node, cst.SimpleStatementLine):
                for el in node.body:
                    if isinstance(el, cst.Assign):
                        for t in el.targets:
                            if isinstance(t.target, cst.Name): names.add(t.target.value)
        return names - top_defs

    def _fix_file(self, file_path: Path) -> bool:
        try:
            old_code = file_path.read_text(encoding="utf-8")
            if not old_code.strip(): return False
            
            module = cst.parse_module(old_code)
            
            # 1. Inserir Import
            if not has_nexus_import(module):
                module = insert_import_safely(module, self.nexus_import)

            # 2. Coletar Globais
            globals_ = self._collect_globals(module)
            
            # 3. Aplicar Transformações com Metadados
            wrapper = cst.MetadataWrapper(module)
            new_tree = wrapper.visit(GlobalToContextTransformer(globals_))
            new_tree = new_tree.visit(NexusExecuteTransformer(self.target_parent))
            
            new_code = new_tree.code
            if old_code == new_code: return False

            if self.dry_run:
                logger.info(f"🔍 [DRY RUN] Mudanças detectadas em {file_path}")
                return True

            with tempfile.NamedTemporaryFile(delete=False, suffix=".py", dir=file_path.parent) as tmp:
                tmp.write(new_code.encode("utf-8"))
                tmp_path = Path(tmp.name)

            if self._validate_syntax(tmp_path):
                shutil.move(str(tmp_path), str(file_path))
                logger.info(f"✨ Cristalizado: {file_path.name}")
                return True
            else:
                tmp_path.unlink()
                return False
        except Exception as e:
            logger.error(f"🚨 Erro em {file_path.name}: {e}")
            return False

    def crystallize(self):
        if not self.dry_run: self._create_checkpoint()
        
        logger.info(f"⚡ Protocolo JARVIS V5.2 | Modo: {'DRY' if self.dry_run else 'LIVE'}")
        count = 0
        
        for py_file in self.base_path.rglob("*.py"):
            # Pula pastas proibidas e arquivos de ignore
            if any(part in self.forbidden_dirs for part in py_file.parts): continue
            if py_file.name in self.ignore_files: continue
            
            if self._fix_file(py_file):
                count += 1
        
        logger.info(f"🏁 Finalizado. {count} arquivos processados.")

if __name__ == "__main__":
    ProjectCrystallizer(dry_run=DRY_RUN).crystallize()
