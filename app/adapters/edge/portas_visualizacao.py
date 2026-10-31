# -*- coding: utf-8 -*-
"""Vertente de VISUALIZAÇÃO das portas de navegador.

Somente leitura: lista o catálogo, descreve uma porta e captura a aba atual sem navegar.
Nunca clica, digita nem muda a página. Sempre liberada, como observe_screen no desktop.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.adapters.edge.portas_core import captura_aba_atual, carregar_macros

_MACROS_DIR = Path(__file__).resolve().parents[3] / "data" / "portas" / "macros"


def _resumo(macro: dict[str, Any]) -> dict[str, Any]:
    return {
        "nome": macro["nome"],
        "descricao": macro["descricao"],
        "risco": macro["risco"],
        "parametros": macro["parametros"],
        "dominios_permitidos": macro["dominios_permitidos"],
    }


def registrar_visualizacao_portas(
    mcp: Any,
    tracked_action: Callable[[str], Callable[..., Any]],
    content_fn: Callable[[dict[str, Any]], list[Any]],
    macros_dir: Path = _MACROS_DIR,
) -> None:
    """Registra as tools de visualização. Recebe o decorador e o formatador de imagem do servidor."""
    catalogo = carregar_macros(macros_dir)

    @mcp.tool()
    @tracked_action("Listando portas")
    def portas_listar() -> dict[str, Any]:
        """Lista as portas de navegador disponíveis, com risco e parâmetros. Não executa nada."""
        return {"portas": [_resumo(m) for m in catalogo.values()]}

    @mcp.tool()
    @tracked_action("Descrevendo porta")
    def portas_descrever(nome: str) -> dict[str, Any]:
        """Mostra domínios e tipos de passo de uma porta, para auditoria antes de usá-la."""
        macro = catalogo.get(nome)
        if macro is None:
            return {"success": False, "error": f"porta não existe: {nome}"}
        return {
            "success": True,
            **_resumo(macro),
            "tipos_de_passo": [p["acao"] for p in macro["passos"]],
        }

    @mcp.tool(structured_output=False)
    @tracked_action("Observando aba de portas")
    def portas_observar_aba() -> list[Any]:
        """Captura a aba atual do navegador controlado, sem navegar. Devolve a imagem."""
        try:
            png = captura_aba_atual()
        except Exception as exc:
            return content_fn({"success": False, "error": str(exc)})
        return content_fn({"success": True, "screenshot_base64_bytes": len(png)}, png=png)
