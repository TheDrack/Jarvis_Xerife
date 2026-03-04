# -*- coding: utf-8 -*-
"""
evolve_all_pending.py — Evolução em lote de capacidades JARVIS pendentes.

Pipeline:
  1. Carrega capabilities.jrvs e filtra as pendentes.
  2. Ordena respeitando dependências (topological sort).
  3. Chama evolution_mutator.evolve() para cada cap.
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
from scripts.evolution_mutator import evolve as mutator_evolve, update_capability_status

# Default priority assigned to capabilities that don't specify one
_DEFAULT_PRIORITY = 99


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _load_capabilities(cap_path: str = "data/capabilities.jrvs") -> List[Dict]:
    path = Path(cap_path)
    if not path.exists():
        print(f"❌ {cap_path} não encontrado.")
        sys.exit(1)
    return document_store.read(path).get("capabilities", [])


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
    args = parser.parse_args()

    all_caps = _load_capabilities()
    completed_ids: Set[str] = {c["id"] for c in all_caps if c.get("status") == "complete"}

    if args.cap_id:
        # Modo de cap específica
        target = next((c for c in all_caps if c["id"] == args.cap_id), None)
        if not target:
            print(f"❌ {args.cap_id} não encontrado em capabilities.json")
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

    successes = 0
    failures = 0
    failed_caps: List[str] = []

    for idx, cap in enumerate(pending_ordered, 1):
        cap_id = cap["id"]
        title = cap.get("title", "")
        print(f"\n[{idx}/{total}] 🧬 Evoluindo {cap_id} — {title}")

        try:
            success = mutator_evolve(
                cap_id=cap_id,
                roadmap_context=cap.get("notes", ""),
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
