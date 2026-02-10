# Database Migrations

This directory contains database migration scripts for JARVIS.

## Files

- **001_create_jarvis_capabilities.sql**: Creates the `jarvis_capabilities` table for tracking JARVIS self-awareness capabilities
- **populate_capabilities.py**: Python script to populate the capabilities table from `data/capabilities.json`

## Running Migrations

### Automatic (via SQLModel)

The `jarvis_capabilities` table is automatically created when the application starts,
thanks to SQLModel's `create_all()` functionality.

### Manual (using SQL script)

If you need to manually create the table (e.g., for Supabase), run:

```bash
# For PostgreSQL/Supabase
psql -h your-host -d your-database -U your-user -f migrations/001_create_jarvis_capabilities.sql
```

### Populating Capabilities

After the table is created, populate it with the 102 capabilities:

```bash
python migrations/populate_capabilities.py
```

This script:
1. Loads capabilities from `data/capabilities.json`
2. Inserts or updates each capability in the database
3. Preserves existing status updates (won't override to 'nonexistent' if already changed)

## Capabilities Schema

The `jarvis_capabilities` table tracks:

- **id**: Capability ID (1-102) from JARVIS_OBJECTIVES_MAP
- **chapter**: Chapter name (e.g., "CHAPTER_1_IMMEDIATE_FOUNDATION")
- **capability_name**: Human-readable capability description
- **status**: Implementation status ("nonexistent", "partial", or "complete")
- **requirements**: JSON array of technical requirements
- **implementation_logic**: Description of implementation approach
- **created_at**: Timestamp when capability was first added
- **updated_at**: Timestamp of last update

## Evolution API Endpoints

After running migrations, the following endpoints become available:

- `GET /v1/status/evolution`: Get overall evolution progress
- `GET /v1/evolution/next-step`: Get next capability to implement
- `POST /v1/evolution/scan`: Scan repository for existing capabilities
- `GET /v1/evolution/requirements/{capability_id}`: Get technical requirements

See the API documentation at `/docs` for full details.
