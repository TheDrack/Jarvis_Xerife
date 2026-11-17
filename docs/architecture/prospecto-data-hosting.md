# Prospecto — Data Hosting Decision

**Status:** staged decision; local DuckDB is the current implementation.  
**Decision owner:** Jarvis_Xerife.  
**Scope:** official CNPJ reference data and the read-only discovery engine.

## 1. Requirements

The CNPJ reference dataset is a large analytical dataset, refreshed in monthly releases. It is not the same workload as the commercial application's transactional data.

The hosting design must:
- keep the discovery engine independent from the MultMetal workstation;
- avoid sending raw CNPJ bulk data through a browser or a public frontend;
- support read-only query traffic and controlled dataset refreshes;
- preserve dataset version, source attribution, checksums and ingestion manifests;
- avoid requiring a single local machine to be online for every query;
- keep marketplace accounts, catalogs, agreements and orders in a transactional database.

## 2. Current stage — local DuckDB

For manual validation, the existing DuckDB store remains the simplest option:
- one configured file, selected by `JARVIS_PROSPECTO_STORE_PATH`;
- ingestion is an explicit operation;
- query adapters open the store read-only;
- MCP and HUD use the same adapter contract;
- no database file is committed to Git.

This stage is intentionally host-local. Setting the environment variable on Android does not mount or synchronize the Desktop file.

## 3. Interim hosted option — dedicated Render service with persistent disk

A dedicated private service with a persistent SSD disk can host the DuckDB store and a private discovery API. Mount the disk at a stable path such as `/var/data` and configure `JARVIS_PROSPECTO_STORE_PATH=/var/data/cnpj.duckdb`.

This is suitable for a single-instance internal service, not a final horizontal-scale design:
- Render's default service filesystem is ephemeral; only data under the persistent disk mount survives deploys/restarts.
- A persistent disk is attached to one service instance and cannot be shared with another service.
- A service with an attached disk cannot scale to multiple instances.
- Persistent-disk deploys disable zero-downtime deploys.
- One-off jobs run on separate compute and cannot access the service's persistent disk.

Therefore, if this option is selected, query and ingest must be orchestrated within the same disk-owning service or the dataset must be transferred through an explicit deployment/ingestion process. Do not create a second worker and assume it can mount the same disk.

References:
- Render Persistent Disks: https://render.com/docs/disks
- Render service types: https://render.com/docs/service-types

## 4. Scale path — versioned Parquet in S3-compatible object storage

For multi-client or horizontally scaled discovery, evaluate storing the normalized dataset as partitioned Parquet files in S3-compatible object storage (for example, R2 or S3), rather than sharing a single DuckDB database file between service instances.

DuckDB's `httpfs` extension can read remote HTTP(S) and S3-compatible objects. Parquet partitioning by state and possibly activity prefix allows the query layer to avoid downloading irrelevant partitions when the layout and predicates align.

Proposed flow:

```text
Receita Federal monthly release
          |
  validation + normalization
          |
 immutable dataset version
          |
 partitioned Parquet objects
          |
 S3-compatible object storage
          |
 DuckDB httpfs / local cache
          |
 private Prospecto discovery API
          |
 HUD / Jarvis agents / commercial app
```

Before adopting this:
1. Benchmark a representative query by UF, municipality and CNAE against the actual partition layout.
2. Verify HTTP range requests and partition pruning with the selected object store.
3. Measure cold-cache and warm-cache latency, egress and request costs.
4. Keep each dataset version immutable; update an active-version pointer only after all partitions and manifests validate.
5. Test concurrent readers and dataset refreshes. Never overwrite files that active readers may be querying.
6. Keep a local SSD cache for hot partitions if remote range reads are too slow or expensive.

Reference:
- DuckDB httpfs extension: https://duckdb.org/docs/stable/core_extensions/httpfs/overview
- DuckDB S3 API support: https://duckdb.org/docs/current/core_extensions/httpfs/s3api

## 5. Where Supabase/Postgres fits

Use a transactional database for the commercial application's own state:
- organizations and memberships;
- supplier opt-in and storefront configuration;
- catalog items and availability;
- buyer-supplier relationships;
- quotes and versioned recurring agreements;
- purchase orders and scheduled occurrences;
- billing records when billing is implemented.

Do not default to importing the entire public CNPJ reference dataset into the same OLTP database. PostgreSQL can bulk-load large data with `COPY`, but that does not make it the best analytical storage format for the discovery workload. If a normalized subset is needed for transactional joins, store only the required indexed fields and retain the bulk source in the analytical/object-storage layer.

References:
- Supabase database overview: https://supabase.com/docs/guides/database/overview
- Supabase bulk import guidance: https://supabase.com/docs/guides/database/import-data

## 6. Decision gates

Do not migrate the current DuckDB implementation until one of these triggers is real:
- the Jarvis host is no longer reliably available;
- Android and Desktop need a shared dataset;
- more than one service instance must query the same dataset;
- ingestion cadence or dataset size exceeds the current host's storage/maintenance budget;
- the commercial application needs private service-to-service discovery at production volume.

At that point, benchmark the persistent-disk option against partitioned Parquet/object storage. Keep the public discovery engine and the commercial transaction database separate.
