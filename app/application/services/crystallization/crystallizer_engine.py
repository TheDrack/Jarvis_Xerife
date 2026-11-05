# -*- coding: utf-8 -*-
"""CrystallizerEngine — cria componentes apenas dentro de caminhos autorizados."""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

from app.application.security.repository_path_policy import (
    UnsafeRepositoryPath,
    contains_frozen_directory,
    normalize_relative_path,
    protected_prefix_for,
    resolve_repository_path,
    validate_filename,
)
from app.core.nexus import nexus, NexusComponent

logger = logging.getLogger(__name__)


class CrystallizerEngine(NexusComponent):
    """Motor de cristalização com validação de caminho antes de qualquer escrita."""

    def __init__(self):
        super().__init__()
        self.logger = nexus.resolve("structured_logger")
        self.base_path = str(Path(__file__).resolve().parents[4])

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """Cria um componente usando name, code e um path relativo a app/."""
        if not context or "code" not in context or "name" not in context:
            return {"success": False, "error": "Dados insuficientes para cristalização."}

        return self.crystallize(
            context["name"],
            context["code"],
            context.get("path", "domain/gears"),
        )

    def crystallize(self, name: str, code: str, relative_path: str) -> Dict[str, Any]:
        """Escreve código somente dentro de app/ e fora dos prefixos protegidos.

        Caminhos absolutos, drives Windows, traversal, aliases por symlink e
        destinos em core/capabilities/infraestrutura/segurança são rejeitados.
        """
        try:
            repository_root = Path(self.base_path).resolve()
            safe_relative_path = normalize_relative_path(relative_path)
            safe_name = validate_filename(name)
            target_relative = f"app/{safe_relative_path}/{safe_name}.py"

            target_file, lexical_path, resolved_relative = resolve_repository_path(
                repository_root,
                target_relative,
                reject_symlinks=True,
            )
            protected_prefix = protected_prefix_for(lexical_path) or protected_prefix_for(
                resolved_relative
            )
            if protected_prefix:
                raise UnsafeRepositoryPath(f"destination is protected: {protected_prefix}")
            if contains_frozen_directory(lexical_path) or contains_frozen_directory(
                resolved_relative
            ):
                raise UnsafeRepositoryPath("destination is inside a frozen directory")

            target_file.parent.mkdir(parents=True, exist_ok=True)

            # Revalida após criar os diretórios para não confiar apenas na
            # resolução anterior à operação de filesystem.
            target_file, lexical_path, resolved_relative = resolve_repository_path(
                repository_root,
                target_relative,
                reject_symlinks=True,
            )
            protected_prefix = protected_prefix_for(lexical_path) or protected_prefix_for(
                resolved_relative
            )
            if protected_prefix:
                raise UnsafeRepositoryPath(f"destination is protected: {protected_prefix}")
            if contains_frozen_directory(lexical_path) or contains_frozen_directory(
                resolved_relative
            ):
                raise UnsafeRepositoryPath("destination is inside a frozen directory")

            target_file.write_text(code, encoding="utf-8")

            if self.logger is not None and hasattr(self.logger, "execute"):
                self.logger.execute(
                    {
                        "level": "info",
                        "message": f"💎 Nova gema cristalizada: {safe_name} em {safe_relative_path}",
                    }
                )

            nexus.invalidate_component(safe_name)
            nexus.commit_memory()
            return {"success": True, "path": str(target_file)}

        except UnsafeRepositoryPath as exc:
            return {"success": False, "error": f"Destino de cristalização bloqueado: {exc}"}
        except Exception as exc:
            error_msg = f"💥 Falha na cristalização de {name}: {str(exc)}"
            if self.logger is not None and hasattr(self.logger, "execute"):
                try:
                    self.logger.execute({"level": "error", "message": error_msg})
                except Exception:
                    logger.exception("Falha ao registrar erro de cristalização.")
            return {"success": False, "error": error_msg}
