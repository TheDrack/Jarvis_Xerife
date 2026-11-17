"""Build the materialized prospecting store from the official CNPJ open data.

One monthly load, scoped to the states you actually prospect, then every campaign
query answers from the store instead of rescanning ~30 GB of CSV. Files already
loaded are skipped, so an interrupted run resumes where it stopped.

Example:
    python scripts/prospecto_ingest.py \\
        --data-dir /dados/receita/2026-11 \\
        --db /dados/receita/prospecto-2026-11.duckdb \\
        --uf SC
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.adapters.infrastructure.prospecting import (
    CnpjStoreBuilder,
    CnpjStoreFiles,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Jarvis Prospecto CNPJ store.")
    parser.add_argument("--data-dir", required=True, help="directory with extracted CNPJ CSVs")
    parser.add_argument("--db", required=True, help="DuckDB file to build")
    parser.add_argument("--uf", action="append", required=True, help="state to materialize (repeatable)")
    parser.add_argument("--establishments", action="append", help="explicit establishments CSV")
    parser.add_argument("--companies", action="append", help="explicit companies CSV")
    parser.add_argument("--municipalities", help="explicit municipalities CSV")
    parser.add_argument("--cnaes", help="explicit CNAEs CSV")
    parser.add_argument("--simples", help="optional Simples/MEI CSV")
    parser.add_argument("--legal-natures", help="optional Naturezas CSV")
    parser.add_argument("--qualifications", help="optional Qualificacoes CSV")
    parser.add_argument("--countries", help="optional Paises CSV")
    parser.add_argument("--situation-reasons", help="optional Motivos CSV")
    parser.add_argument("--memory-limit", default="2GB", help="DuckDB memory limit (default 2GB)")
    parser.add_argument("--threads", type=int, default=4, help="DuckDB threads (default 4)")
    parser.add_argument("--force", action="store_true", help="recreate the store from scratch")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_dir = Path(args.data_dir)

    establishments = (
        tuple(Path(path) for path in args.establishments)
        if args.establishments
        else tuple(sorted(data_dir.glob("Estabelecimentos*.csv")))
    )
    companies = (
        tuple(Path(path) for path in args.companies)
        if args.companies
        else tuple(sorted(data_dir.glob("Empresas*.csv")))
    )
    files = CnpjStoreFiles(
        establishments=establishments,
        companies=companies,
        municipalities=Path(args.municipalities) if args.municipalities else data_dir / "Municipios.csv",
        cnaes=Path(args.cnaes) if args.cnaes else data_dir / "Cnaes.csv",
        simples=Path(args.simples) if args.simples else (
            data_dir / "Simples.csv" if (data_dir / "Simples.csv").is_file() else None
        ),
        legal_natures=Path(args.legal_natures) if args.legal_natures else (
            data_dir / "Naturezas.csv" if (data_dir / "Naturezas.csv").is_file() else None
        ),
        qualifications=Path(args.qualifications) if args.qualifications else (
            data_dir / "Qualificacoes.csv" if (data_dir / "Qualificacoes.csv").is_file() else None
        ),
        countries=Path(args.countries) if args.countries else (
            data_dir / "Paises.csv" if (data_dir / "Paises.csv").is_file() else None
        ),
        situation_reasons=Path(args.situation_reasons) if args.situation_reasons else (
            data_dir / "Motivos.csv" if (data_dir / "Motivos.csv").is_file() else None
        ),
    )

    builder = CnpjStoreBuilder(
        args.db,
        scope_ufs=tuple(args.uf),
        memory_limit=args.memory_limit,
        threads=args.threads,
    )
    try:
        report = builder.build(files, force=args.force)
    except FileNotFoundError as error:
        print(f"erro: {error}", file=sys.stderr)
        return 2

    print(f"store: {report.database}")
    print(f"estados materializados: {', '.join(uf.upper() for uf in args.uf)}")
    print(f"estabelecimentos: {report.establishment_rows} | empresas: {report.company_rows}")
    print(f"arquivos auxiliares opcionais: {sum(path is not None for path in (files.simples, files.legal_natures, files.qualifications, files.countries, files.situation_reasons))}")
    print(f"arquivos carregados agora: {len(report.ingested_files)}")
    for name in report.ingested_files:
        print(f"  + {name}")
    print(f"arquivos ja carregados antes (ignorados): {len(report.skipped_files)}")
    print("proximo passo: prospecto_run.py --store " + str(report.database))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
