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

DRY_RUN = True  # Altere para False para execução real

# =========================
# Utils de Estrutura
# =========================
def has_nexus_import(module: cst.Module) -> bool:
    """Verifica se o componente Nexus já está importado."""
    for stmt in module.body:
        if isinstance(stmt, cst.SimpleStatementLine):
            code = module.code_for_node(stmt).lower()
            if "nexuscomponent" in code:
                return True
    return False

def insert_import_safely(module: cst.Module, import_stmt: str) -> cst.Module:
    """Insere o import respeitando docstrings e __future__."""
    body = list(module.body)
    insert_at = 0
    
    # Pular Docstring
    if body and isinstance(body[0], cst.SimpleStatementLine):
        first = body[0].body[0]
        if isinstance(first, cst.Expr) and isinstance(first.value, cst.SimpleString):
            insert_at = 1
            
    # Pular __future__ imports
    while insert_at < len(body):
        stmt = body[insert_at]
        if isinstance(stmt, cst.SimpleStatementLine):
            if any(isinstance(el, cst.ImportFrom) and el.module and el.module.value == "__future__" 
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
        # Herança robusta
        is_already_child = any(
            (isinstance(b.value, cst.Name) and b.value.value == self.target_parent) or
            (isinstance(b.value, cst.Attribute) and b.value.attr.value == self.target_parent)
            for b in bases
        )
        if not is_already_child:
            bases.insert(0, cst.Arg(value=cst.Name(self.target_parent)))

        body = list(updated_node.body.body)
        if not any(isinstance(b, cst.FunctionDef) and b.name.value == "execute" for b in body):
            # Criação do método execute padrão
            body.append(cst.FunctionDef(
                name=cst.Name("execute"),
                params=cst.Parameters(params=[
                    cst.Param(name=cst.Name("self")),
                    cst.Param(name=cst.Name("context"), annotation=cst.Annotation(cst.Name("dict"))),
                ]),
                body=cst.IndentedBlock(body=[cst.SimpleStatementLine([cst.Pass()])]),
            ))
        return updated_node.with_changes(bases=tuple(bases), body=updated_node.body.with_changes(body=tuple(body)))

class GlobalToContextTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (ScopeProvider, QualifiedNameProvider)

    def __init__(self, global_names: Set[str]):
        self.global_names = global_names
        self.local_defs_stack: List[Set[str]] = []

    def visit_FunctionDef(self, node: cst.FunctionDef):
        # Tracking de variáveis locais para evitar shadowing
        self.local_defs_stack.append({p.name.value for p in node.params.params})

    def leave_FunctionDef(self, node: cst.FunctionDef):
        self.local_defs_stack.pop()

    def visit_AssignTarget(self, node: cst.AssignTarget):
        if self.local_defs_stack and isinstance(node.target, cst.Name):
            self.local_defs_stack[-1].add(node.target.value)

    def _is_shadowed(self, name: str) -> bool:
        return any(name in scope for scope in self.local_defs_stack)

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name):
        qnames = self.get_metadata(QualifiedNameProvider, original_node)
        if not qnames: return updated_node
        
        name = next(iter(qnames)).name
        scope = self.get_metadata(ScopeProvider, original_node)

        # Transforma acesso: VAR -> context.get('VAR')
        if (name in self.global_names and isinstance(scope, FunctionScope) 
            and isinstance(scope.parent, GlobalScope) and not self._is_shadowed(name)):
            return cst.Call(
                func=cst.Attribute(value=cst.Name("context"), attr=cst.Name("get")),
                args=[cst.Arg(cst.SimpleString(f"'{name}'"))],
            )
        return updated_node

    def leave_Assign(self, original_node: cst.Assign, updated_node: cst.Assign):
        if not self.local_defs_stack: return updated_node
        new_targets = []
        for t in updated_node.targets:
            if isinstance(t.target, cst.Name) and t.target.value in self.global_names and not self._is_shadowed(t.target.value):
                # Transforma atribuição: VAR = x -> context['VAR'] = x
                new_targets.append(cst.AssignTarget(target=cst.Subscript(
                    value=cst.Name("context"),
                    slice=[cst.SubscriptElement(slice=cst.Index(value=cst.SimpleString(f"'{t.target.value}'")))]
                )))
            else:
                new_targets.append(t)
        return updated_node.with_changes(targets=new_targets)

    def leave_AugAssign(self, original_node: cst.AugAssign, updated_node: cst.AugAssign):
        """Melhoria: Proteção de tipo no AugAssign (+=, -=, etc)"""
        if not self.local_defs_stack: return updated_node
        if isinstance(updated_node.target, cst.Name) and updated_node.target.value in self.global_names and not self._is_shadowed(updated_node.target.value):
            name = updated_node.target.value
            
            # Tenta inferir se é numérico para o fallback, senão usa None
            fallback_val = cst.Integer("0") if isinstance(updated_node.value, (cst.Integer, cst.Float)) else cst.Name("None")
            
            return cst.Assign(
                targets=[cst.AssignTarget(target=cst.Subscript(
                    value=cst.Name("context"),
                    slice=[cst.SubscriptElement(slice=cst.Index(value=cst.SimpleString(f"'{name}'")))]
                ))],
                value=cst.BinaryOperation(
                    left=cst.Call(
                        func=cst.Attribute(value=cst.Name("context"), attr=cst.Name("get")),
                        args=[cst.Arg(cst.SimpleString(f"'{name}'")), cst.Arg(fallback_val)],
                    ),
                    operator=updated_node.operator,
                    right=updated_node.value,
                ),
            )
        return updated_node

# =========================
# Engine Principal
# =========================
class ProjectCrystallizer:
    def __init__(self, dry_run: bool = True):
        self.base_path = Path(".").resolve()
        self.dry_run = dry_run
        self.forbidden_dirs = {"core", "infrastructure", ".git", "venv", "__pycache__", "backups"}
        self.ignore_files = {"__init__.py", "nexus.py", "crystallizer.py"}
        self.nexus_import = "from app.core.nexuscomponent import NexusComponent"
        self.target_parent = "NexusComponent"

    def _create_checkpoint(self):
        backup_dir = self.base_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = backup_dir / f"checkpoint_{ts}.tar.gz"
        logger.info(f"📦 Backup de segurança gerado: {archive.name}")
        with tarfile.open(archive, "w:gz") as tar:
            for root, dirs, files in os.walk(self.base_path):
                dirs[:] = [d for d in dirs if d not in self.forbidden_dirs]
                for f in files:
                    if f.endswith(".py"):
                        full = Path(root) / f
                        tar.add(full, arcname=full.relative_to(self.base_path))

    def _validate_syntax(self, path: Path) -> bool:
        try:
            py_compile.compile(str(path), doraise=True)
            return True
        except Exception as e:
            logger.warning(f"⚠️ Erro de sintaxe detectado em {path.name}: {e}")
            return False

    def _collect_globals(self, module: cst.Module) -> Set[str]:
        """Identifica variáveis globais candidatas à migração para Context."""
        names, top_defs = set(), set()
        for node in module.body:
            if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
                top_defs.add(node.name.value)
            elif isinstance(node, cst.SimpleStatementLine):
                for el in node.body:
                    if isinstance(el, cst.Assign):
                        for t in el.targets:
                            if isinstance(t.target, cst.Name): names.add(t.target.value)
                    elif isinstance(el, (cst.AnnAssign, cst.AugAssign)) and isinstance(el.target, cst.Name):
                        names.add(el.target.value)
        return names - top_defs

    def _fix_file(self, file_path: Path) -> bool:
        try:
            old_code = file_path.read_text(encoding="utf-8")
            if not old_code.strip(): return False
            
            module = cst.parse_module(old_code)
            if not has_nexus_import(module):
                module = insert_import_safely(module, self.nexus_import)

            globals_ = self._collect_globals(module)
            if globals_:
                logger.info(f"🔍 {file_path.name}: {len(globals_)} globais encontradas para cristalização.")

            wrapper = cst.MetadataWrapper(module)
            new_tree = wrapper.visit(GlobalToContextTransformer(globals_))
            new_tree = new_tree.visit(NexusExecuteTransformer(self.target_parent))
            new_code = new_tree.code

            if old_code == new_code:
                return False

            if self.dry_run:
                diff = list(difflib.unified_diff(
                    old_code.splitlines(), new_code.splitlines(), 
                    fromfile=f"a/{file_path.name}", tofile=f"b/{file_path.name}", lineterm=""
                ))
                if diff:
                    print(f"\n--- PROPOSTA DE MUDANÇA: {file_path.relative_to(self.base_path)} ---\n" + "\n".join(diff))
                return True

            # Escrita segura com arquivo temporário
            fd, tmp = tempfile.mkstemp(dir=file_path.parent, suffix=".py", text=True)
            tmp_path = Path(tmp)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f: 
                    f.write(new_code)
                if self._validate_syntax(tmp_path):
                    shutil.move(tmp, file_path)
                    logger.info(f"✨ Arquivo cristalizado com sucesso: {file_path.name}")
                    return True
                else:
                    logger.error(f"❌ Abortando alteração em {file_path.name}: Falha na validação de sintaxe.")
                    tmp_path.unlink()
                    return False
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                raise e
        except Exception as e:
            logger.error(f"🚨 Falha crítica no processamento de {file_path.name}: {e}")
            return False

    def crystallize(self):
        if not self.dry_run: 
            self._create_checkpoint()
        
        logger.info(f"⚡ Protocolo de Cristalização JARVIS V5.2 ({'MODO TESTE' if self.dry_run else 'EXECUTANDO LIVE'})")
        count = 0
        for root, dirs, files in os.walk(self.base_path):
            dirs[:] = [d for d in dirs if d not in self.forbidden_dirs]
            for f in files:
                if f.endswith(".py") and f not in self.ignore_files:
                    if self._fix_file(Path(root) / f): 
                        count += 1
        
        logger.info(f"🏁 Protocolo finalizado. {count} arquivos analisados/modificados.")

if __name__ == "__main__":
    # Inicialização direta conforme solicitado
    ProjectCrystallizer(dry_run=DRY_RUN).crystallize()
