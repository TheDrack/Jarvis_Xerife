"""Materialized store for the Receita Federal CNPJ open dataset.

The raw dataset is ~30 GB of CSV per month and ~70 million establishments. Reading
it per campaign is wasteful and, in plain Python, slow. This module follows the
methodology for large tabular data: filter while reading, keep bounded memory,
work per source file so an interrupted load can resume, and persist a scoped,
queryable copy for repeated use.

DuckDB is used instead of SQLite because the access pattern is analytical
(filter and join over millions of rows, few columns), and because it reads the
CSV directly with a memory limit and spills to disk. SQLite is row-oriented and
its row-by-row load cost dominates at this scale; it remains a fine choice for
transactional state, not for scanning this dataset.

Only the requested UF scope is materialized: a national copy is not needed to
prospect four municipalities, and keeping it would multiply disk and time.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.adapters.infrastructure.prospecting.cnpj_open_data import (
    DATASET_LICENSE,
    DATASET_URL,
)
from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectEvidenceType,
    RegistryPresence,
)
from app.domain.prospecting.discovery import DiscoveryQuery, DiscoveryResult
from app.domain.prospecting.icp import normalize_text

# Official "novo layout": 29 documented fields, 30 in the current extract (an extra
# phone column was added). Names beyond the documented ones are labelled generically.
ESTABELECIMENTO_COLUMNS: tuple[str, ...] = (
    "cnpj_basico",
    "cnpj_ordem",
    "cnpj_dv",
    "matriz_filial",
    "nome_fantasia",
    "situacao_cadastral",
    "data_situacao_cadastral",
    "motivo_situacao_cadastral",
    "cidade_exterior",
    "pais",
    "data_inicio_atividade",
    "cnae_principal",
    "cnae_secundaria",
    "tipo_logradouro",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "cep",
    "uf",
    "municipio",
    "ddd1",
    "telefone1",
    "ddd2",
    "telefone2",
    "ddd_fax",
    "telefone3",
    "correio_eletronico",
    "situacao_especial",
    "data_situacao_especial",
)
MINIMUM_ESTABLISHMENT_COLUMNS = 21
_ACTIVE = "02"
_SUPPORTED_FIELDS = ("company_name", "legal_name", "cnpj", "industry", "city", "state", "company_size", "legal_nature", "capital_social", "opening_date", "establishment_type", "neighborhood", "postal_code", "primary_cnae", "has_phone", "has_email", "has_fax")


@dataclass(frozen=True)
class CnpjStoreFiles:
    """Source files for one monthly load."""

    establishments: tuple[Path, ...]
    companies: tuple[Path, ...]
    municipalities: Path
    cnaes: Path
    simples: Optional[Path] = None
    legal_natures: Optional[Path] = None
    qualifications: Optional[Path] = None
    countries: Optional[Path] = None
    situation_reasons: Optional[Path] = None

    def missing(self) -> tuple[str, ...]:
        missing = [
            path.name
            for path in (*self.establishments, *self.companies, self.municipalities, self.cnaes, *((self.simples,) if self.simples else ()), *((self.legal_natures,) if self.legal_natures else ()), *((self.qualifications,) if self.qualifications else ()), *((self.countries,) if self.countries else ()), *((self.situation_reasons,) if self.situation_reasons else ()))
            if not path.is_file()
        ]
        return tuple(missing)


@dataclass(frozen=True)
class CnpjStoreReport:
    """What the load produced, per file and in total."""

    database: Path
    ingested_files: tuple[str, ...]
    skipped_files: tuple[str, ...]
    establishment_rows: int
    company_rows: int


def _column_spec(path: Path, *, encoding: str, delimiter: str) -> dict[str, str]:
    """Columns for one establishments file, tolerating the extra trailing field."""
    with path.open("r", encoding=encoding, newline="") as handle:
        first = next(csv.reader(handle, delimiter=delimiter), [])
    width = len(first)
    if width < MINIMUM_ESTABLISHMENT_COLUMNS:
        raise ValueError(
            f"{path.name} has {width} columns; expected at least {MINIMUM_ESTABLISHMENT_COLUMNS}"
        )
    names = list(ESTABELECIMENTO_COLUMNS[:width])
    names.extend(f"extra_{index}" for index in range(len(names), width))
    return {name: "VARCHAR" for name in names}


def _columns_sql(spec: dict[str, str]) -> str:
    return ", ".join(f"'{name}': '{dtype}'" for name, dtype in spec.items())


class CnpjStoreBuilder:
    """Build or extend a scoped DuckDB store from the official CSVs."""

    def __init__(
        self,
        database: Path | str,
        *,
        scope_ufs: tuple[str, ...],
        memory_limit: str = "2GB",
        threads: int = 4,
        encoding: str = "latin-1",
        delimiter: str = ";",
    ) -> None:
        if not scope_ufs:
            raise ValueError("scope_ufs must name at least one state")
        self._database = Path(database)
        self._scope_ufs = tuple(uf.upper() for uf in scope_ufs)
        self._memory_limit = memory_limit
        self._threads = threads
        self._encoding = encoding
        self._delimiter = delimiter

    def _connect(self):
        import duckdb  # imported lazily: the CSV adapter works without this extra

        connection = duckdb.connect(str(self._database))
        connection.execute(f"SET memory_limit = '{self._memory_limit}'")
        connection.execute(f"SET threads = {int(self._threads)}")
        connection.execute("SET preserve_insertion_order = false")
        return connection

    def _create_schema(self, connection) -> None:
        columns = ", ".join(f"{name} VARCHAR" for name in ESTABELECIMENTO_COLUMNS)
        connection.execute(f"CREATE TABLE IF NOT EXISTS establishments ({columns})")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS companies ("
            "cnpj_basico VARCHAR, razao_social VARCHAR, natureza VARCHAR, "
            "qualificacao VARCHAR, capital VARCHAR, porte VARCHAR, ente VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS municipalities (codigo VARCHAR, nome VARCHAR)"
        )
        connection.execute("CREATE TABLE IF NOT EXISTS cnaes (codigo VARCHAR, descricao VARCHAR)")
        connection.execute("CREATE TABLE IF NOT EXISTS legal_natures (codigo VARCHAR, descricao VARCHAR)")
        connection.execute("CREATE TABLE IF NOT EXISTS qualifications (codigo VARCHAR, descricao VARCHAR)")
        connection.execute("CREATE TABLE IF NOT EXISTS countries (codigo VARCHAR, descricao VARCHAR)")
        connection.execute("CREATE TABLE IF NOT EXISTS situation_reasons (codigo VARCHAR, descricao VARCHAR)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS simples (cnpj_basico VARCHAR, opcao_simples VARCHAR, "
            "data_opcao_simples VARCHAR, data_exclusao_simples VARCHAR, opcao_mei VARCHAR, "
            "data_opcao_mei VARCHAR, data_exclusao_mei VARCHAR)"
        )
        # Backward-compatible migration for stores created by the earlier 3-column schema.
        for name in ("natureza", "qualificacao", "capital", "ente"):
            connection.execute(f"ALTER TABLE companies ADD COLUMN IF NOT EXISTS {name} VARCHAR")

        connection.execute(
            "CREATE TABLE IF NOT EXISTS ingest_log (file_name VARCHAR, rows BIGINT, "
            "ingested_at VARCHAR)"
        )

    def _already_ingested(self, connection) -> set[str]:
        rows = connection.execute("SELECT file_name FROM ingest_log").fetchall()
        return {row[0] for row in rows}

    def build(self, files: CnpjStoreFiles, *, force: bool = False) -> CnpjStoreReport:
        """Load every not-yet-ingested file, then resolve companies and lookups.

        Re-running after an interruption skips files already logged, so a 30 GB
        load does not restart from zero. ``force`` rebuilds the database file.
        """
        missing = files.missing()
        if missing:
            raise FileNotFoundError("Receita Federal open-data files not found: " + ", ".join(missing))

        self._database.parent.mkdir(parents=True, exist_ok=True)
        if force and self._database.exists():
            self._database.unlink()

        connection = self._connect()
        try:
            self._create_schema(connection)
            ingested = self._already_ingested(connection)
            new_files: list[str] = []
            skipped: list[str] = []

            scope_placeholders = ", ".join("?" for _ in self._scope_ufs)
            for path in files.establishments:
                if path.name in ingested:
                    skipped.append(path.name)
                    continue
                spec = _column_spec(path, encoding=self._encoding, delimiter=self._delimiter)
                connection.execute(
                    # BY NAME keeps older 29-column extracts and the current 30-column
                    # layout working against the same table.
                    "INSERT INTO establishments BY NAME "
                    f"SELECT * FROM read_csv(?, delim=?, quote='\"', escape='\"', header=false, "
                    "columns={" + _columns_sql(spec) + "}, encoding=?, ignore_errors=true) "
                    f"WHERE uf IN ({scope_placeholders})",
                    [str(path), self._delimiter, self._encoding, *self._scope_ufs],
                )
                rows = connection.execute(
                    "SELECT count(*) FROM establishments WHERE uf IN ("
                    + scope_placeholders
                    + ")",
                    list(self._scope_ufs),
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO ingest_log VALUES (?, ?, ?)",
                    [path.name, int(rows), datetime.now(timezone.utc).isoformat()],
                )
                new_files.append(path.name)
                ingested.add(path.name)

            for path in files.companies:
                if path.name in ingested:
                    skipped.append(path.name)
                    continue
                connection.execute(
                    "INSERT INTO companies (cnpj_basico, razao_social, natureza, qualificacao, capital, porte, ente) "
                    "SELECT cnpj_basico, razao_social, natureza, qualificacao, capital, porte, ente FROM read_csv(?, delim=?, "
                    "quote='\"', escape='\"', header=false, columns={'cnpj_basico': 'VARCHAR', "
                    "'razao_social': 'VARCHAR', 'natureza': 'VARCHAR', 'qualificacao': 'VARCHAR', "
                    "'capital': 'VARCHAR', 'porte': 'VARCHAR', 'ente': 'VARCHAR'}, "
                    "encoding=?, ignore_errors=true) "
                    "WHERE cnpj_basico IN (SELECT DISTINCT cnpj_basico FROM establishments)",
                    [str(path), self._delimiter, self._encoding],
                )
                connection.execute(
                    "INSERT INTO ingest_log VALUES (?, ?, ?)",
                    [path.name, 0, datetime.now(timezone.utc).isoformat()],
                )
                new_files.append(path.name)
                ingested.add(path.name)

            connection.execute("DELETE FROM municipalities")
            connection.execute(
                "INSERT INTO municipalities SELECT column0, column1 FROM read_csv(?, delim=?, "
                "quote='\"', header=false, columns={'column0': 'VARCHAR', 'column1': 'VARCHAR'}, "
                "encoding=?, ignore_errors=true)",
                [str(files.municipalities), self._delimiter, self._encoding],
            )
            connection.execute("DELETE FROM simples")
            if files.simples is not None:
                connection.execute(
                    "INSERT INTO simples SELECT * FROM read_csv(?, delim=?, quote='\"', "
                    "escape='\"', header=false, columns={'cnpj_basico':'VARCHAR', "
                    "'opcao_simples':'VARCHAR', 'data_opcao_simples':'VARCHAR', "
                    "'data_exclusao_simples':'VARCHAR', 'opcao_mei':'VARCHAR', "
                    "'data_opcao_mei':'VARCHAR', 'data_exclusao_mei':'VARCHAR'}, "
                    "encoding=?, ignore_errors=true)",
                    [str(files.simples), self._delimiter, self._encoding],
                )
                new_files.append(files.simples.name)
            for source_path, table_name in (
                (files.legal_natures, "legal_natures"),
                (files.qualifications, "qualifications"),
                (files.countries, "countries"),
                (files.situation_reasons, "situation_reasons"),
            ):
                connection.execute(f"DELETE FROM {table_name}")
                if source_path is None:
                    continue
                connection.execute(
                    f"INSERT INTO {table_name} SELECT column0, column1 FROM read_csv(?, delim=?, "
                    "quote='\"', header=false, columns={'column0':'VARCHAR','column1':'VARCHAR'}, "
                    "encoding=?, ignore_errors=true)",
                    [str(source_path), self._delimiter, self._encoding],
                )
                new_files.append(source_path.name)
            connection.execute("DELETE FROM cnaes")
            connection.execute(
                "INSERT INTO cnaes SELECT column0, column1 FROM read_csv(?, delim=?, "
                "quote='\"', header=false, columns={'column0': 'VARCHAR', 'column1': 'VARCHAR'}, "
                "encoding=?, ignore_errors=true)",
                [str(files.cnaes), self._delimiter, self._encoding],
            )

            establishment_rows = connection.execute("SELECT count(*) FROM establishments").fetchone()[0]
            company_rows = connection.execute("SELECT count(*) FROM companies").fetchone()[0]
        finally:
            connection.close()

        return CnpjStoreReport(
            database=self._database,
            ingested_files=tuple(new_files),
            skipped_files=tuple(skipped),
            establishment_rows=int(establishment_rows),
            company_rows=int(company_rows),
        )


class CnpjStoreProvider:
    """Discovery over the materialized store, with the same contract as the CSV adapter."""

    source_id = "receita_federal_cnpj_open_data"
    source_name = "Receita Federal - Dados Abertos do CNPJ"
    license_or_terms = DATASET_LICENSE

    def __init__(self, database: Path | str, *, dataset_url: str = DATASET_URL) -> None:
        self._database = Path(database)
        self._dataset_url = dataset_url

    def _connect(self):
        import duckdb

        if not self._database.is_file():
            raise FileNotFoundError(f"prospecting store not found: {self._database}")
        return duckdb.connect(str(self._database), read_only=True)

    def _municipality_codes(self, connection, names: tuple[str, ...]) -> Optional[list[str]]:
        if not names:
            return None
        wanted = {normalize_text(name) for name in names}
        rows = connection.execute("SELECT codigo, nome FROM municipalities").fetchall()
        codes = [row[0] for row in rows if normalize_text(row[1] or "") in wanted]
        return sorted(set(codes))

    def lookup_company(self, cnpj: str) -> Optional[ProspectCompany]:
        """Look one CNPJ up in the whole store, outside the campaign filter.

        This is how an external lead is checked against the registry: the answer is
        about existence in the extract, not about fitting the current query.
        """
        digits = "".join(ch for ch in cnpj if ch.isdigit())
        if len(digits) != 14:
            return None
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT e.cnpj_basico, e.cnpj_ordem, e.cnpj_dv, e.nome_fantasia, "
                "e.cnae_principal, c.razao_social, m.nome, n.descricao, c.natureza, c.capital, "
                "c.porte, e.data_inicio_atividade, e.matriz_filial, e.bairro, e.cep, "
                "(nullif(trim(e.telefone1), '') IS NOT NULL OR nullif(trim(e.telefone2), '') IS NOT NULL), "
                "(nullif(trim(e.correio_eletronico), '') IS NOT NULL), "
                "(nullif(trim(e.telefone3), '') IS NOT NULL) "
                "FROM establishments e "
                "LEFT JOIN companies c ON c.cnpj_basico = e.cnpj_basico "
                "LEFT JOIN municipalities m ON m.codigo = e.municipio "
                "LEFT JOIN cnaes n ON n.codigo = e.cnae_principal "
                "WHERE e.cnpj_basico = ? AND e.cnpj_ordem = ? AND e.cnpj_dv = ? LIMIT 1",
                [digits[:8], digits[8:12], digits[12:]],
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None

        (basename, ordem, dv, trade_name, cnae, legal_name, municipality_name, description, legal_nature, capital_social, company_size, opening_date, establishment_type, neighborhood, postal_code, has_phone, has_email, has_fax) = row
        name = (trade_name or "").strip() or (legal_name or "").strip()
        if not name or not any(ch.isalpha() for ch in name):
            return None
        reference = datetime.now(timezone.utc)
        return ProspectCompany(
            company_name=name,
            legal_name=(legal_name or "").strip() or None,
            cnpj="".join(ch for ch in f"{basename}{ordem}{dv}" if ch.isdigit()),
            industry=description or f"CNAE {cnae}",
            primary_cnae=cnae,
            legal_nature=(legal_nature or "").strip() or None,
            capital_social=(capital_social or "").strip() or None,
            company_size=(company_size or "").strip() or None,
            opening_date=(opening_date or "").strip() or None,
            establishment_type=(establishment_type or "").strip() or None,
            neighborhood=(neighborhood or "").strip() or None,
            postal_code=(postal_code or "").strip() or None,
            has_phone=bool(has_phone),
            has_email=bool(has_email),
            has_fax=bool(has_fax),
            city=municipality_name,
            country="BR",
            registry_presence=RegistryPresence.FOUND,
            evidence=(
                ProspectEvidence(
                    source_id=self.source_id,
                    source_name=self.source_name,
                    source_type=ProspectEvidenceType.PUBLIC_REGISTRY,
                    url=self._dataset_url,
                    license_or_terms=self.license_or_terms,
                    supports_fields=_SUPPORTED_FIELDS,
                    collected_at=reference,
                ),
            ),
        )

    def discover(
        self,
        query: DiscoveryQuery,
        *,
        collected_at: Optional[datetime] = None,
    ) -> DiscoveryResult:
        reference = collected_at or datetime.now(timezone.utc)
        connection = self._connect()
        try:
            municipalities = self._municipality_codes(connection, query.municipalities)

            conditions = ["e.uf = ?"]
            parameters: list[object] = [query.uf]
            if query.after_cnpj_basico:
                conditions.append("e.cnpj_basico > ?")
                parameters.append(query.after_cnpj_basico)
            if query.situation_codes:
                placeholders = ", ".join("?" for _ in query.situation_codes)
                conditions.append(f"e.situacao_cadastral IN ({placeholders})")
                parameters.extend(query.situation_codes)
            elif query.only_active:
                conditions.append("e.situacao_cadastral = ?")
                parameters.append(_ACTIVE)
            if query.country_codes:
                placeholders = ", ".join("?" for _ in query.country_codes)
                conditions.append(f"e.pais IN ({placeholders})")
                parameters.extend(query.country_codes)
            if query.reason_codes:
                placeholders = ", ".join("?" for _ in query.reason_codes)
                conditions.append(f"e.motivo_situacao_cadastral IN ({placeholders})")
                parameters.extend(query.reason_codes)
            if query.special_situation_codes:
                placeholders = ", ".join("?" for _ in query.special_situation_codes)
                conditions.append(f"e.situacao_especial IN ({placeholders})")
                parameters.extend(query.special_situation_codes)
            if query.has_phone is True:
                conditions.append("(length(trim(coalesce(e.telefone1, ''))) > 0 OR length(trim(coalesce(e.telefone2, ''))) > 0)")
            elif query.has_phone is False:
                conditions.append("(coalesce(e.telefone1, '') = '' AND coalesce(e.telefone2, '') = '')")
            if query.has_email is True:
                conditions.append("length(trim(coalesce(e.correio_eletronico, ''))) > 0")
            elif query.has_email is False:
                conditions.append("coalesce(e.correio_eletronico, '') = ''")
            if query.has_fax is True:
                conditions.append("length(trim(coalesce(e.telefone3, ''))) > 0")
            elif query.has_fax is False:
                conditions.append("coalesce(e.telefone3, '') = ''")
            if query.establishment_types:
                placeholders = ", ".join("?" for _ in query.establishment_types)
                conditions.append(f"e.matriz_filial IN ({placeholders})")
                parameters.extend(query.establishment_types)
            if query.neighborhoods:
                placeholders = ", ".join("?" for _ in query.neighborhoods)
                conditions.append(f"upper(coalesce(e.bairro, '')) IN ({placeholders})")
                parameters.extend(value.upper() for value in query.neighborhoods)
            if query.postal_codes:
                placeholders = ", ".join("?" for _ in query.postal_codes)
                conditions.append(f"regexp_replace(coalesce(e.cep, ''), '[^0-9]', '', 'g') IN ({placeholders})")
                parameters.extend("".join(ch for ch in value if ch.isdigit()) for value in query.postal_codes)
            if query.opened_from:
                conditions.append("e.data_inicio_atividade >= ?")
                parameters.append(query.opened_from)
            if query.opened_to:
                conditions.append("e.data_inicio_atividade <= ?")
                parameters.append(query.opened_to)
            if query.company_sizes:
                placeholders = ", ".join("?" for _ in query.company_sizes)
                conditions.append(f"c.porte IN ({placeholders})")
                parameters.extend(query.company_sizes)
            if query.legal_natures:
                placeholders = ", ".join("?" for _ in query.legal_natures)
                conditions.append(f"c.natureza IN ({placeholders})")
                parameters.extend(query.legal_natures)
            if query.capital_min is not None:
                conditions.append("try_cast(replace(c.capital, ',', '.') AS DOUBLE) >= ?")
                parameters.append(query.capital_min)
            if query.capital_max is not None:
                conditions.append("try_cast(replace(c.capital, ',', '.') AS DOUBLE) <= ?")
                parameters.append(query.capital_max)
            if (query.simples_only or query.mei_only) and connection.execute("SELECT count(*) FROM simples").fetchone()[0] == 0:
                raise RuntimeError("Simples/MEI filters require the official Simples dataset to be ingested")
            if query.simples_only:
                conditions.append("EXISTS (SELECT 1 FROM simples sn WHERE sn.cnpj_basico=e.cnpj_basico AND sn.opcao_simples='S')")
            if query.mei_only:
                conditions.append("EXISTS (SELECT 1 FROM simples sm WHERE sm.cnpj_basico=e.cnpj_basico AND sm.opcao_mei='S')")
            if municipalities is not None:
                if not municipalities:
                    return DiscoveryResult(
                        source_id=self.source_id,
                        collected_at=reference,
                        notes=(
                            "no official municipality matched the requested names",
                            f"source dataset: {self._dataset_url} (CC-BY, attribute the Receita Federal)",
                        ),
                    )
                placeholders = ", ".join("?" for _ in municipalities)
                conditions.append(f"e.municipio IN ({placeholders})")
                parameters.extend(municipalities)
            cnae_conditions = " OR ".join("e.cnae_principal LIKE ?" for _ in query.cnae_prefixes)
            parameters.extend(f"{prefix}%" for prefix in query.cnae_prefixes)
            if query.include_secondary_cnae:
                # Secondary activities are a comma-separated list of codes; match a
                # code token, never a substring in the middle of another code.
                pattern = "(^|,)\\s*(" + "|".join(query.cnae_prefixes) + ")"
                cnae_conditions += " OR regexp_matches(coalesce(e.cnae_secundaria, ''), ?)"
                parameters.append(pattern)
            conditions.append(f"({cnae_conditions})")

            where = " AND ".join(conditions)
            matched_rows = connection.execute(
                f"SELECT count(*) FROM establishments e LEFT JOIN companies c ON c.cnpj_basico=e.cnpj_basico WHERE {where}", parameters
            ).fetchone()[0]

            rows = connection.execute(
                "SELECT e.cnpj_basico, e.cnpj_ordem, e.cnpj_dv, e.nome_fantasia, "
                "e.cnae_principal, e.municipio, c.razao_social, m.nome, n.descricao, "
                "c.natureza, c.capital, c.porte, e.data_inicio_atividade, e.matriz_filial, "
                "e.bairro, e.cep, "
                "(nullif(trim(e.telefone1), '') IS NOT NULL OR nullif(trim(e.telefone2), '') IS NOT NULL), "
                "(nullif(trim(e.correio_eletronico), '') IS NOT NULL), "
                "(nullif(trim(e.telefone3), '') IS NOT NULL) "
                "FROM establishments e "
                "LEFT JOIN companies c ON c.cnpj_basico = e.cnpj_basico "
                "LEFT JOIN municipalities m ON m.codigo = e.municipio "
                "LEFT JOIN cnaes n ON n.codigo = e.cnae_principal "
                f"WHERE {where} ORDER BY e.cnpj_basico, e.cnpj_ordem LIMIT ?",
                [*parameters, query.limit],
            ).fetchall()
        finally:
            connection.close()

        next_cursor = rows[-1][0].strip() if rows and int(matched_rows) > query.limit else None
        companies: list[ProspectCompany] = []
        seen: set[str] = set()
        masked = 0
        for (
            basename,
            ordem,
            dv,
            trade_name,
            cnae,
            _municipality_code,
            legal_name,
            municipality_name,
            cnae_description,
            legal_nature,
            capital_social,
            company_size,
            opening_date,
            establishment_type,
            neighborhood,
            postal_code,
            has_phone,
            has_email,
            has_fax,
        ) in rows:
            basename = (basename or "").strip()
            if basename in seen:
                continue
            name = (trade_name or "").strip() or (legal_name or "").strip()
            if not name or not any(ch.isalpha() for ch in name):
                masked += 1
                continue
            digits = "".join(ch for ch in f"{basename}{ordem}{dv}" if ch.isdigit())
            if len(digits) != 14:
                masked += 1
                continue
            seen.add(basename)
            companies.append(
                ProspectCompany(
                    company_name=name,
                    legal_name=(legal_name or "").strip() or None,
                    cnpj=digits,
                    industry=cnae_description or f"CNAE {cnae}",
                    primary_cnae=cnae,
                    legal_nature=(legal_nature or "").strip() or None,
                    capital_social=(capital_social or "").strip() or None,
                    company_size=(company_size or "").strip() or None,
                    opening_date=(opening_date or "").strip() or None,
                    establishment_type=(establishment_type or "").strip() or None,
                    neighborhood=(neighborhood or "").strip() or None,
                    postal_code=(postal_code or "").strip() or None,
                    has_phone=bool(has_phone),
                    has_email=bool(has_email),
                    has_fax=bool(has_fax),
                    city=municipality_name,
                    state=query.uf,
                    country="BR",
                    registry_presence=RegistryPresence.FOUND,
                    evidence=(
                        ProspectEvidence(
                            source_id=self.source_id,
                            source_name=self.source_name,
                            source_type=ProspectEvidenceType.PUBLIC_REGISTRY,
                            url=self._dataset_url,
                            license_or_terms=self.license_or_terms,
                            supports_fields=_SUPPORTED_FIELDS,
                            collected_at=reference,
                        ),
                    ),
                )
            )

        notes = [
            f"source dataset: {self._dataset_url} (CC-BY, attribute the Receita Federal)",
            "answers read from the materialized store",
        ]
        truncated = int(matched_rows) > query.limit
        if truncated:
            notes.append(
                f"page limited to {query.limit} companies of {int(matched_rows)} matches; "
                f"continue with after_cnpj_basico={next_cursor}. Results follow CNPJ "
                "base order, not a priority ranking"
            )

        return DiscoveryResult(
            source_id=self.source_id,
            companies=tuple(companies),
            scanned_rows=int(matched_rows),
            matched_rows=int(matched_rows),
            skipped_malformed_rows=masked,
            truncated=truncated,
            next_cursor=next_cursor,
            collected_at=reference,
            notes=tuple(notes),
        )


__all__ = [
    "CnpjStoreBuilder",
    "CnpjStoreFiles",
    "CnpjStoreProvider",
    "CnpjStoreReport",
    "ESTABELECIMENTO_COLUMNS",
]
