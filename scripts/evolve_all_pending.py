# -*- coding: utf-8 -*-
"""
evolve_all_pending.py — Evolução em lote de capacidades JARVIS pendentes.

Pipeline:
  1. Carrega capabilities.jrvs e filtra as pendentes.
  2. Ordena respeitando dependências (topological sort).
  3. Chama o EvolutionOrchestrator (via Nexus) para cada cap.
  4. Loga progresso e contagem de sucesso/falha ao final.

Uso:
  python scripts/evolve_all_pending.py [--dry-run] [--limit N] [--cap-id CAP-042] [--delay 2.0]
"""
import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

# Adiciona o root do projeto ao path para imports locais
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.utils.document_store import document_store

# Default priority assigned to capabilities that don't specify one
_DEFAULT_PRIORITY = 99


# ---------------------------------------------------------------------------
# Motor de evolução
# ---------------------------------------------------------------------------

def _get_orchestrator():
    """Resolve o EvolutionOrchestrator via Nexus.

    Nota: o antigo motor ``scripts/evolution_mutator.py`` foi removido do
    projeto; o ``EvolutionOrchestrator`` é hoje o caminho vivo de mutação
    (gera o patch, valida a sintaxe, salva a proposta e abre o PR).
    """
    from app.core.nexus import nexus

    try:
        orchestrator = nexus.resolve("evolution_orchestrator")
    except Exception as exc:  # pragma: no cover - depende do registry em runtime
        print(f"❌ evolution_orchestrator indisponível no Nexus: {exc}")
        return None
    if orchestrator is None or not hasattr(orchestrator, "execute"):
        print("❌ evolution_orchestrator indisponível no Nexus.")
        return None
    return orchestrator


def evolve(cap_id: str, roadmap_context: str = "", max_attempts: int = 3) -> bool:
    """Evolui uma capability, tentando até *max_attempts* ciclos.

    Retorna True apenas quando o EvolutionOrchestrator conclui um ciclo com
    sucesso (proposta válida gerada).
    """
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        return False

    attempts = max(1, int(max_attempts or 1))
    for attempt in range(1, attempts + 1):
        result = orchestrator.execute(
            {
                "cap_id": cap_id,
                "mission_id": cap_id,
                "roadmap_context": roadmap_context,
            }
        ) or {}
        if result.get("success"):
            if attempt > 1:
                print(f"  ℹ️  Succeeded on attempt {attempt}/{attempts}")
            return True
        reason = result.get("reason") or result.get("error") or "unknown"
        print(f"  ⚠️  Tentativa {attempt}/{attempts} falhou: {reason}")
    return False


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _load_capabilities(cap_path: str = "data/capabilities.jrvs") -> List[Dict]:
    """Carrega capabilities de *cap_path* com fallback automático para .json."""
    path = Path(cap_path)
    if path.exists():
        try:
            return document_store.read(path).get("capabilities", [])
        except Exception as exc:
            print(f"⚠️  Falha ao ler {path}: {exc}")
    # Fallback: tenta o equivalente .json
    json_path = path.with_suffix(".json")
    if json_path.exists():
        print(f"⚠️  Usando fallback: {json_path}")
        try:
            return document_store.read(json_path).get("capabilities", [])
        except Exception as exc:
            print(f"❌ Fallback também falhou: {exc}")
    print(f"❌ Nenhum arquivo de capabilities encontrado ({cap_path} / {json_path}).")
    sys.exit(1)


def _topological_sort(caps: List[Dict], completed_ids: Set[str]) -> List[Dict]:
    """
    Retorna caps pendentes em ordem topológica:
    uma cap só é enfileirada quando todas as suas depends_on estão em completed_ids
    (ou já foram enfileiradas antes dela nesta rodada).
    """
    pending = {c["id"]: c for c in caps if c.get("status") != "complete"}
    resolved: List[Dict] = []
    resolved_ids: Set[str] = set(completed_ids)
    remaining = list(pending.values())
    # Ordena por prioridade para que caps de alta prioridade sejam preferidas
    remaining.sort(key=lambda x: x.get("priority", _DEFAULT_PRIORITY))

    max_iterations = len(remaining) + 1
    iteration = 0
    while remaining and iteration < max_iterations:
        iteration += 1
        progress = False
        still_pending = []
        for cap in remaining:
            deps = set(cap.get("depends_on", []))
            if deps.issubset(resolved_ids):
                resolved.append(cap)
                resolved_ids.add(cap["id"])
                progress = True
            else:
                still_pending.append(cap)
        remaining = still_pending
        if not progress:
            # Dependências circulares ou deps faltando — adiciona o restante na ordem atual
            resolved.extend(remaining)
            break

    return resolved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Evolução em lote de capacidades JARVIS")
    parser.add_argument("--dry-run", action="store_true", help="Lista sem executar")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de caps a evoluir")
    parser.add_argument("--cap-id", help="Evolve apenas uma cap específica (ex: CAP-042)")
    parser.add_argument(
        "--delay", type=float, default=2.0, help="Segundos entre caps (padrão: 2.0)"
    )
    parser.add_argument("--max-attempts", type=int, default=3, help="Tentativas por cap")
    parser.add_argument(
        "--roadmap-context",
        default=None,
        help="Contexto textual da missão (substitui as notas da capability)",
    )
    args = parser.parse_args()

    all_caps = _load_capabilities()
    completed_ids: Set[str] = {c["id"] for c in all_caps if c.get("status") == "complete"}

    if args.cap_id:
        # Modo de cap específica
        target = next((c for c in all_caps if c["id"] == args.cap_id), None)
        if not target:
            print(f"❌ {args.cap_id} não encontrado em capabilities.jrvs")
            sys.exit(1)
        pending_ordered = [target]
    else:
        pending_ordered = _topological_sort(all_caps, completed_ids)

    if args.limit:
        pending_ordered = pending_ordered[: args.limit]

    total = len(pending_ordered)
    print(f"📋 {total} cap(s) pendente(s) para evolução.\n")

    if args.dry_run:
        print("🔍 DRY-RUN — nenhuma alteração será feita:\n")
        for idx, cap in enumerate(pending_ordered, 1):
            deps = ", ".join(cap.get("depends_on", [])) or "—"
            print(f"  {idx:3}. {cap['id']} | prioridade {cap.get('priority','?')} | deps: {deps}")
            print(f"       {cap.get('title','')}")
        print()
        sys.exit(0)

    import os
    if os.environ.get("EVOLUTION_ENABLED", "").strip().lower() != "true":
        print("⏸️ Autoevolução pausada: defina EVOLUTION_ENABLED=true explicitamente para mutações.")
        sys.exit(2)

    successes = 0
    failures = 0
    failed_caps: List[str] = []

    for idx, cap in enumerate(pending_ordered, 1):
        cap_id = cap["id"]
        title = cap.get("title", "")
        print(f"\n[{idx}/{total}] 🧬 Evoluindo {cap_id} — {title}")

        try:
            success = evolve(
                cap_id=cap_id,
                roadmap_context=args.roadmap_context or cap.get("notes", ""),
                max_attempts=args.max_attempts,
            )
            if success:
                successes += 1
                completed_ids.add(cap_id)
                print(f"  ✅ {cap_id} concluído.")
            else:
                failures += 1
                failed_caps.append(cap_id)
                print(f"  ❌ {cap_id} falhou.")
        except Exception as exc:
            failures += 1
            failed_caps.append(cap_id)
            print(f"  ❌ {cap_id} erro inesperado: {exc}")

        if idx < total and args.delay > 0:
            time.sleep(args.delay)

    # Resumo final
    print(f"\n{'='*50}")
    print(f"📊 RESULTADO FINAL")
    print(f"   Total processado : {total}")
    print(f"   ✅ Sucesso        : {successes}")
    print(f"   ❌ Falha          : {failures}")
    if failed_caps:
        print(f"   Falhas           : {', '.join(failed_caps)}")
    print(f"{'='*50}\n")

    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
