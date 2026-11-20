"""Run one Jarvis Prospecto campaign against the official CNPJ open data.

Reads a campaign file (ICP + discovery query), scans the locally extracted
Receita Federal CSVs, qualifies every candidate and writes the client-facing CSV
plus a run manifest. It performs no network calls, stores nothing else and
contacts nobody.

The manifest is the point of the exercise: it records the exact query, profile,
dataset counters and reference time, so next month's run can be compared instead
of guessed.

Example:
    python scripts/prospecto_run.py \\
        --campaign config/prospecting/campaigns/jarvis-prospecto-grande-florianopolis.json \\
        --data-dir /dados/receita \\
        --out artifacts/prospecto
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.adapters.infrastructure.prospecting import (
    CnpjOpenDataAdapter,
    CnpjOpenDataFiles,
    CnpjStoreProvider,
    CompositeDiscoveryProvider,
    ExternalLeadsAdapter,
)
from app.application.prospecting import (
    CampaignDefinition,
    build_snapshot,
    diff_snapshots,
    format_diff,
    load_campaign,
    load_latest_snapshot,
    run_campaign,
    save_snapshot,
    write_run_outputs,
)
from app.domain.prospecting.filters import describe_catalog, load_filter_catalog

DEFAULT_FILES = {
    "establishments": "Estabelecimentos0.csv",
    "companies": "Empresas0.csv",
    "municipalities": "Municipios.csv",
    "cnaes": "Cnaes.csv",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Jarvis Prospecto campaign offline.")
    parser.add_argument("--campaign", help="campaign JSON file")
    parser.add_argument("--data-dir", help="directory with extracted CNPJ CSVs")
    parser.add_argument(
        "--store",
        help="materialized DuckDB store (skips CSV scanning; see prospecto_ingest.py)",
    )
    parser.add_argument("--out", default="artifacts/prospecto", help="output directory")
    parser.add_argument("--establishments", help="override establishments CSV path")
    parser.add_argument("--companies", help="override companies CSV path")
    parser.add_argument("--municipalities", help="override municipalities CSV path")
    parser.add_argument("--cnaes", help="override CNAEs CSV path")
    parser.add_argument("--limit", type=int, help="override the page size (companies per discovery page)")
    parser.add_argument(
        "--max-companies",
        type=int,
        help="safety ceiling for the run (default: exhaust the filter)",
    )
    parser.add_argument(
        "--preset",
        help="predefined filter preset id; replaces the campaign query for this run",
    )
    parser.add_argument(
        "--filters",
        default=str(REPO_ROOT / "config/prospecting/filters.json"),
        help="filter catalog JSON (default: config/prospecting/filters.json)",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="print the available filter presets and exit",
    )
    parser.add_argument(
        "--include-unqualified",
        action="store_true",
        help="include not_fit companies in the CSV",
    )
    parser.add_argument(
        "--history",
        help="directory for run snapshots (default: <out>/history)",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="do not persist a snapshot or print the monthly diff",
    )
    parser.add_argument(
        "--geocode",
        action="store_true",
        help="geocode delivered Brazilian companies using the local CNEFE dataset",
    )
    parser.add_argument(
        "--geocoding-db",
        help="DuckDB cache for geocoding results (default: ~/.local/share/jarvis/prospecto/geocoding.duckdb)",
    )
    parser.add_argument(
        "--external-leads",
        help="CSV with leads that are not in the registry (referral, site, inbound)",
    )
    parser.add_argument(
        "--external-source-url",
        help="URL where the external leads came from (required with --external-leads)",
    )
    parser.add_argument(
        "--external-source-name",
        help="label for the external lead source (optional)",
    )
    parser.add_argument("--now", help="ISO-8601 reference time for a reproducible run")
    return parser


def _resolve(base: Path, override: str | None, key: str) -> Path:
    return Path(override) if override else base / DEFAULT_FILES[key]


def _apply_preset(campaign: CampaignDefinition, preset_id: str, catalog_path: str) -> CampaignDefinition:
    catalog = load_filter_catalog(catalog_path)
    preset = catalog.get(preset_id)
    return CampaignDefinition.model_validate(
        {**campaign.model_dump(), "query": preset.query.model_dump()}
    )


def _build_geocoding_service(database: str | Path | None = None):
    """Build the optional local CNEFE geocoder without affecting default startup."""
    from app.adapters.infrastructure.prospecting.geocodebr_geocoder import GeocodeBrGeocoder
    from app.adapters.infrastructure.prospecting.geocoding_store import DuckDBGeocodingRepository
    from app.application.services.prospecting.geocoding import GeocodingService

    configured_database = (
        database
        or os.getenv("JARVIS_PROSPECTO_GEOCODING_DB")
        or Path.home() / ".local" / "share" / "jarvis" / "prospecto" / "geocoding.duckdb"
    )
    cache_path = Path(configured_database).expanduser()
    return GeocodingService(
        GeocodeBrGeocoder(),
        DuckDBGeocodingRepository(cache_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_presets:
        print(describe_catalog(load_filter_catalog(args.filters)))
        return 0
    if not args.campaign:
        print("erro: informe --campaign (ou use --list-presets)", file=sys.stderr)
        return 2

    if args.geocoding_db and not args.geocode:
        print("erro: --geocoding-db exige --geocode", file=sys.stderr)
        return 2

    campaign = load_campaign(args.campaign)
    if args.preset:
        try:
            campaign = _apply_preset(campaign, args.preset, args.filters)
        except KeyError as error:
            print(f"erro: {error.args[0]}", file=sys.stderr)
            return 2
    if args.limit is not None:
        campaign = CampaignDefinition.model_validate(
            {
                **campaign.model_dump(),
                "query": {**campaign.query.model_dump(), "limit": args.limit},
            }
        )

    now = datetime.fromisoformat(args.now).astimezone(timezone.utc) if args.now else None

    if args.store:
        registry = CnpjStoreProvider(Path(args.store))
    elif args.data_dir:
        data_dir = Path(args.data_dir)
        files = CnpjOpenDataFiles(
            establishments=_resolve(data_dir, args.establishments, "establishments"),
            companies=_resolve(data_dir, args.companies, "companies"),
            municipalities=_resolve(data_dir, args.municipalities, "municipalities"),
            cnaes=_resolve(data_dir, args.cnaes, "cnaes"),
        )
        registry = CnpjOpenDataAdapter(files)
    else:
        print("erro: informe --data-dir ou --store", file=sys.stderr)
        return 2

    provider = registry
    if args.external_leads:
        if not args.external_source_url:
            print(
                "erro: --external-leads exige --external-source-url (de onde vieram os leads)",
                file=sys.stderr,
            )
            return 2
        external = ExternalLeadsAdapter(
            Path(args.external_leads),
            source_url=args.external_source_url,
            **(
                {"source_name": args.external_source_name}
                if args.external_source_name
                else {}
            ),
        )
        provider = CompositeDiscoveryProvider(registry, external)

    try:
        geocoding_service = (
            _build_geocoding_service(args.geocoding_db) if args.geocode else None
        )
        run = run_campaign(
            provider,
            campaign,
            now=now,
            include_unqualified=args.include_unqualified,
            max_companies=args.max_companies,
            geocoding_service=geocoding_service,
        )
    except (FileNotFoundError, RuntimeError, ValueError, TypeError, ImportError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 2

    try:
        csv_path, manifest_path = write_run_outputs(run, args.out)
    except FileExistsError as error:
        print(f"erro: {error}", file=sys.stderr)
        return 2

    manifest = run.manifest
    print(f"campanha: {manifest.campaign_name} ({manifest.campaign_id})")
    print(f"fonte: {manifest.source_id}")
    print(f"paginas: {manifest.pages} | linhas lidas: {manifest.scanned_rows} | casadas: {manifest.matched_rows}")
    print(f"empresas descobertas: {manifest.discovered_companies}")
    print(f"entregues no CSV: {manifest.delivered_rows} | fora do ICP: {manifest.excluded_not_fit}")
    print(f"a verificar: {manifest.needs_verification}")
    if manifest.geocoding_enabled:
        print(
            "geocodificacao: "
            f"tentativas={manifest.geocoding_attempted} | "
            f"precisas={manifest.geocoding_success} | "
            f"parciais={manifest.geocoding_partial} | "
            f"sem resultado={manifest.geocoding_failed} | "
            f"sem endereco={manifest.geocoding_skipped}"
        )
        if manifest.coordinate_reference_system:
            print(f"crs: {manifest.coordinate_reference_system}")
    if manifest.truncated:
        print(f"aviso: teto de {manifest.max_companies} empresas atingido; o filtro tem mais resultados")
    for note in manifest.discovery_notes:
        print(f"nota: {note}")
    print(f"csv: {csv_path}")
    print(f"manifesto: {manifest_path}")

    if not args.no_history:
        history_dir = Path(args.history) if args.history else Path(args.out) / "history"
        previous = load_latest_snapshot(history_dir, manifest.campaign_id)
        snapshot = build_snapshot(
            run.rows,
            campaign_id=manifest.campaign_id,
            source_id=manifest.source_id,
            generated_at=manifest.generated_at,
            include_unqualified=args.include_unqualified,
        )
        try:
            save_snapshot(snapshot, history_dir)
        except FileExistsError as error:
            print(f"erro: {error}", file=sys.stderr)
            return 2
        print(format_diff(diff_snapshots(previous, snapshot)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
