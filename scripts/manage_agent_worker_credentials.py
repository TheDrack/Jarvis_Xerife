#!/usr/bin/env python3
"""Provision or revoke one-time Jarvis worker credentials.

The command requires a trusted PostgreSQL connection. The raw token is printed
once for secure transfer to the matching worker's secret store; it is never
written to the database or a file.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine

from app.adapters.infrastructure.agent_worker_credentials import (
    AgentWorkerCredentialStore,
    SUPPORTED_WORKER_CAPABILITIES,
    worker_token_env_name,
)


def _database_url() -> str:
    value = (
        os.getenv("JARVIS_TASK_QUEUE_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not value:
        raise RuntimeError(
            "Set JARVIS_TASK_QUEUE_DATABASE_URL or DATABASE_URL to the shared PostgreSQL database."
        )
    if not value.startswith(("postgres://", "postgresql://", "postgresql+")):
        raise RuntimeError("Worker credentials can only be provisioned against PostgreSQL.")
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    issue = commands.add_parser("issue", help="issue or rotate one agent credential")
    issue.add_argument("--agent-id", required=True)
    issue.add_argument("--principal-id")
    issue.add_argument(
        "--capability",
        action="append",
        choices=sorted(SUPPORTED_WORKER_CAPABILITIES),
        help="server-granted capability; repeat to select more than one",
    )
    issue.add_argument("--expires-hours", type=int, default=720)

    revoke = commands.add_parser("revoke", help="revoke all active credentials for one agent")
    revoke.add_argument("--agent-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "issue" and not 1 <= args.expires_hours <= 2160:
        print("--expires-hours must be between 1 and 2160 (90 days).", file=sys.stderr)
        return 2

    engine = None
    try:
        engine = create_engine(_database_url(), pool_pre_ping=True)
        store = AgentWorkerCredentialStore(engine)
        if args.command == "issue":
            principal_id = args.principal_id or f"worker:{args.agent_id}"
            capabilities = args.capability or ["text_reasoning"]
            token = store.issue(
                agent_id=args.agent_id,
                principal_id=principal_id,
                available_tools=capabilities,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=args.expires_hours),
            )
            print(f"Credential issued. Store this value in {worker_token_env_name(args.agent_id)}:")
            print(token)
            print("This token is shown only once. Reissuing revokes the previous active token.")
            return 0

        revoked = store.revoke_agent(args.agent_id)
        print(f"Revoked {revoked} active credential(s) for agent {args.agent_id}.")
        return 0
    except Exception as exc:
        print(f"Worker credential operation failed ({type(exc).__name__}).", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
