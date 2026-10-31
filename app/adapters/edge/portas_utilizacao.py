# -*- coding: utf-8 -*-
"""Vertente de UTILIZAÇÃO das portas de navegador.

Executa macros. Macros com risco 'acao' (clicar/digitar) exigem user_confirmed=true,
assim como click_at no desktop. Macros de leitura rodam sem confirmação extra.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.adapters.edge.portas_core import carregar_macros, executar

_MACROS_DIR = Path(__file__).resolve().parents[3] / "data" / "portas" / "macros"


def executar_porta(macro: dict[str, Any], params: dict[str, Any] | None, user_confirmed: bool) -> dict[str, Any]:
    if macro["risco"] == "acao" and not user_confirmed:
        return {
            "success": False,
            "status": "confirmation_required",
            "message": "Peça autorização ao usuário antes de executar uma porta de ação.",
        }
    try:
        return {"success": True, "saidas": executar(macro, params or {})}
    except (ValueError, PermissionError, RuntimeError) as exc:
        return {"success": False, "error": str(exc)}


def _criar_porta(macro: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    # fábrica: evita que a variável do laço vire parâmetro da assinatura MCP
    def porta(params: dict[str, Any] | None = None, user_confirmed: bool = False) -> dict[str, Any]:
        return executar_porta(macro, params, user_confirmed)
    return porta


def registrar_utilizacao_portas(
    mcp: Any,
    tracked_action: Callable[[str], Callable[..., Any]],
    macros_dir: Path = _MACROS_DIR,
) -> list[str]:
    registradas: list[str] = []
    for macro in carregar_macros(macros_dir).values():
        nome = f"porta_{macro['nome']}"
        descricao = (
            f"{macro['descricao']}. Risco: {macro['risco']}. "
            f"Domínios: {', '.join(macro['dominios_permitidos'])}. "
            "Portas de risco 'acao' exigem user_confirmed=true."
        )
        mcp.add_tool(
            tracked_action(f"Executando porta {macro['nome']}")(_criar_porta(macro)),
            name=nome,
            description=descricao,
        )
        registradas.append(nome)
    return registradas
