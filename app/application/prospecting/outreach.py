from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Channel(StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    PHONE = "phone"
    WEB_FORM = "web_form"


class PlanStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ContactAuthorization:
    """Traceable legal/operational review for one proposed contact."""

    basis: str
    evidence_ref: str
    reviewed_by: str


@dataclass(frozen=True)
class OutreachPlan:
    plan_id: str
    company_id: str
    channel: Channel
    destination: str
    subject: str | None
    body: str
    campaign_id: str
    status: PlanStatus
    created_at: str


class OutreachTransport(Protocol):
    def send(
        self,
        *,
        destination: str,
        subject: str | None,
        body: str,
        metadata: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: str) -> str:
    return hashlib.sha256(value.strip().casefold().encode("utf-8")).hexdigest()


def _validate_destination(channel: Channel, destination: str) -> str:
    value = destination.strip()
    if not value:
        raise ValueError("destination_required")
    if channel == Channel.EMAIL:
        if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("invalid_email_destination")
    elif channel in (Channel.WHATSAPP, Channel.PHONE):
        normalized = re.sub(r"[\s().-]", "", value)
        if not re.fullmatch(r"\+[1-9]\d{7,14}", normalized):
            raise ValueError("phone_must_be_e164")
        value = normalized
    elif channel == Channel.WEB_FORM:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("web_form_requires_https_url")
    return value


class SQLiteOutreachStore:
    """Durable local store with unique campaign targets and atomic dispatch claims."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(Path(database).expanduser())
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outreach_plans (
                    plan_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    destination_hash TEXT NOT NULL,
                    subject TEXT,
                    body TEXT NOT NULL,
                    campaign_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    authorization_basis TEXT NOT NULL,
                    authorization_evidence_ref TEXT NOT NULL,
                    authorization_reviewed_by TEXT NOT NULL,
                    approved_by TEXT,
                    approved_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(company_id, channel, destination_hash, campaign_id)
                );
                CREATE TABLE IF NOT EXISTS outreach_blocks (
                    block_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    destination_hash TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL,
                    recorded_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(company_id, channel, destination_hash)
                );
                CREATE TABLE IF NOT EXISTS outreach_dispatches (
                    dispatch_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL REFERENCES outreach_plans(plan_id),
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    provider_id TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outreach_events (
                    event_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_outreach_company
                    ON outreach_plans(company_id, created_at);
                CREATE INDEX IF NOT EXISTS ix_outreach_status
                    ON outreach_plans(status, created_at);
                CREATE INDEX IF NOT EXISTS ix_outreach_events_plan
                    ON outreach_events(plan_id, created_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database, timeout=15, isolation_level=None, factory=_ClosingConnection
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    def create_plan(
        self, *, company_id: str, channel: Channel, destination: str,
        subject: str | None, body: str, campaign_id: str,
        authorization: ContactAuthorization,
    ) -> OutreachPlan:
        plan_id, now = uuid.uuid4().hex, _now()
        destination_hash = _digest(destination)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if self._is_blocked(db, company_id, channel, destination_hash):
                db.rollback()
                raise PermissionError("do_not_contact")
            try:
                db.execute(
                    """INSERT INTO outreach_plans (
                        plan_id, company_id, channel, destination, destination_hash,
                        subject, body, campaign_id, status, authorization_basis,
                        authorization_evidence_ref, authorization_reviewed_by,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (plan_id, company_id, channel.value, destination, destination_hash,
                     subject, body, campaign_id, PlanStatus.PENDING_APPROVAL.value,
                     authorization.basis, authorization.evidence_ref,
                     authorization.reviewed_by, now, now),
                )
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise ValueError("duplicate_outreach") from exc
            self._event(db, plan_id, "plan_created", "system", {
                "company_id": company_id, "channel": channel.value,
                "destination_hash": destination_hash, "campaign_id": campaign_id,
                "authorization_basis": authorization.basis,
            })
            db.commit()
        return self.get_plan(plan_id)

    @staticmethod
    def _is_blocked(db: sqlite3.Connection, company_id: str, channel: Channel,
                    destination_hash: str) -> bool:
        return db.execute(
            """SELECT 1 FROM outreach_blocks
               WHERE company_id=? AND channel IN (?, '*')
                 AND (destination_hash='' OR destination_hash=?)
               LIMIT 1""",
            (company_id, channel.value, destination_hash),
        ).fetchone() is not None

    @staticmethod
    def _event(db: sqlite3.Connection, plan_id: str, event: str, actor: str,
               metadata: Mapping[str, Any]) -> None:
        db.execute(
            """INSERT INTO outreach_events
               (event_id, plan_id, event, actor, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (uuid.uuid4().hex, plan_id, event, actor,
             json.dumps(dict(metadata), sort_keys=True), _now()),
        )

    def get_plan(self, plan_id: str) -> OutreachPlan:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM outreach_plans WHERE plan_id=?", (plan_id,)
            ).fetchone()
        if row is None:
            raise LookupError("outreach_plan_not_found")
        return OutreachPlan(
            plan_id=row["plan_id"], company_id=row["company_id"],
            channel=Channel(row["channel"]), destination=row["destination"],
            subject=row["subject"], body=row["body"], campaign_id=row["campaign_id"],
            status=PlanStatus(row["status"]), created_at=row["created_at"],
        )

    def list_events(self, plan_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT event, actor, metadata_json, created_at
                   FROM outreach_events WHERE plan_id=? ORDER BY created_at, rowid""",
                (plan_id,),
            ).fetchall()
        return [
            {"event": row["event"], "actor": row["actor"],
             "metadata": json.loads(row["metadata_json"]), "created_at": row["created_at"]}
            for row in rows
        ]

    def block_contact(self, *, company_id: str, channel: Channel | None,
                      destination: str | None, reason: str, recorded_by: str) -> None:
        if not reason.strip() or not recorded_by.strip():
            raise ValueError("block_reason_and_actor_required")
        digest = _digest(destination) if destination else ""
        channel_value = channel.value if channel is not None else "*"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """INSERT OR IGNORE INTO outreach_blocks
                   (block_id, company_id, channel, destination_hash, reason, recorded_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (uuid.uuid4().hex, company_id, channel_value, digest,
                 reason, recorded_by, _now()),
            )
            rows = db.execute(
                """SELECT plan_id FROM outreach_plans
                   WHERE company_id=? AND (?='*' OR channel=?) AND status IN (?, ?)
                     AND (?='' OR destination_hash=?)""",
                (company_id, channel_value, channel_value, PlanStatus.PENDING_APPROVAL.value,
                 PlanStatus.APPROVED.value, digest, digest),
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE outreach_plans SET status=?, updated_at=? WHERE plan_id=?",
                    (PlanStatus.BLOCKED.value, _now(), row["plan_id"]),
                )
                self._event(db, row["plan_id"], "contact_blocked", recorded_by,
                            {"reason": reason, "channel": channel.value})
            db.commit()

    def approve(self, plan_id: str, approved_by: str) -> OutreachPlan:
        if not approved_by.strip():
            raise ValueError("approver_required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM outreach_plans WHERE plan_id=?", (plan_id,)
            ).fetchone()
            if row is None:
                db.rollback()
                raise LookupError("outreach_plan_not_found")
            channel = Channel(row["channel"])
            if self._is_blocked(db, row["company_id"], channel, row["destination_hash"]):
                db.execute(
                    "UPDATE outreach_plans SET status=?, updated_at=? WHERE plan_id=?",
                    (PlanStatus.BLOCKED.value, _now(), plan_id),
                )
                db.commit()
                raise PermissionError("do_not_contact")
            if row["status"] != PlanStatus.PENDING_APPROVAL.value:
                db.rollback()
                raise ValueError("plan_not_pending_approval")
            now = _now()
            db.execute(
                """UPDATE outreach_plans SET status=?, approved_by=?, approved_at=?, updated_at=?
                   WHERE plan_id=?""",
                (PlanStatus.APPROVED.value, approved_by, now, now, plan_id),
            )
            self._event(db, plan_id, "plan_approved", approved_by, {})
            db.commit()
        return self.get_plan(plan_id)

    def claim_dispatch(self, plan_id: str, idempotency_key: str) -> tuple[OutreachPlan, bool]:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key_required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM outreach_plans WHERE plan_id=?", (plan_id,)
            ).fetchone()
            if row is None:
                db.rollback()
                raise LookupError("outreach_plan_not_found")
            existing = db.execute(
                "SELECT * FROM outreach_dispatches WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                if existing["plan_id"] != plan_id:
                    db.rollback()
                    raise ValueError("idempotency_key_reused")
                db.commit()
                return self.get_plan(plan_id), False
            if row["status"] == PlanStatus.SENT.value:
                db.commit()
                return self.get_plan(plan_id), False
            if row["status"] != PlanStatus.APPROVED.value:
                db.rollback()
                raise PermissionError("approval_required")
            channel = Channel(row["channel"])
            if self._is_blocked(db, row["company_id"], channel, row["destination_hash"]):
                db.execute(
                    "UPDATE outreach_plans SET status=?, updated_at=? WHERE plan_id=?",
                    (PlanStatus.BLOCKED.value, _now(), plan_id),
                )
                db.commit()
                raise PermissionError("do_not_contact")
            now = _now()
            db.execute(
                "INSERT INTO outreach_dispatches VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
                (uuid.uuid4().hex, plan_id, idempotency_key, "sending", now, now),
            )
            db.execute(
                "UPDATE outreach_plans SET status=?, updated_at=? WHERE plan_id=?",
                (PlanStatus.SENDING.value, now, plan_id),
            )
            self._event(db, plan_id, "delivery_started", "system", {
                "channel": channel.value, "destination_hash": row["destination_hash"],
            })
            db.commit()
        return self.get_plan(plan_id), True

    def finish_dispatch(self, plan_id: str, idempotency_key: str, *,
                        success: bool, provider_id: str | None = None,
                        error_code: str | None = None) -> OutreachPlan:
        status = PlanStatus.SENT if success else PlanStatus.FAILED
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now = _now()
            db.execute(
                """UPDATE outreach_dispatches SET status=?, provider_id=?, error_code=?, updated_at=?
                   WHERE plan_id=? AND idempotency_key=?""",
                ("sent" if success else "failed", provider_id, error_code, now,
                 plan_id, idempotency_key),
            )
            db.execute(
                "UPDATE outreach_plans SET status=?, updated_at=? WHERE plan_id=?",
                (status.value, now, plan_id),
            )
            self._event(db, plan_id, "delivery_sent" if success else "delivery_failed",
                        "system", {"provider_id": provider_id, "error_code": error_code})
            db.commit()
        return self.get_plan(plan_id)


class OutreachService:
    def __init__(self, store: SQLiteOutreachStore,
                 transports: Mapping[Channel, OutreachTransport] | None = None) -> None:
        self.store = store
        self.transports = dict(transports or {})

    def create_plan(self, *, company_id: str, channel: Channel, destination: str,
                    subject: str | None, body: str, campaign_id: str,
                    authorization: ContactAuthorization) -> OutreachPlan:
        if not company_id.strip() or not campaign_id.strip() or not body.strip():
            raise ValueError("company_campaign_and_message_required")
        if not isinstance(channel, Channel):
            channel = Channel(channel)
        if authorization.basis not in {"consent", "contractual_relationship",
                                       "legitimate_interest_reviewed"}:
            raise ValueError("authorization_basis_not_supported")
        if not authorization.evidence_ref.strip() or not authorization.reviewed_by.strip():
            raise ValueError("authorization_evidence_required")
        if channel == Channel.EMAIL and not (subject or "").strip():
            raise ValueError("email_subject_required")
        normalized = _validate_destination(channel, destination)
        return self.store.create_plan(
            company_id=company_id.strip(), channel=channel, destination=normalized,
            subject=subject, body=body.strip(), campaign_id=campaign_id.strip(),
            authorization=authorization,
        )

    def get_plan(self, plan_id: str) -> OutreachPlan:
        return self.store.get_plan(plan_id)

    def approve_plan(self, plan_id: str, *, approved_by: str) -> OutreachPlan:
        return self.store.approve(plan_id, approved_by)

    def block_contact(self, *, company_id: str, channel: Channel | None,
                      destination: str | None, reason: str, recorded_by: str) -> None:
        self.store.block_contact(
            company_id=company_id, channel=Channel(channel) if channel is not None else None, destination=destination,
            reason=reason, recorded_by=recorded_by,
        )

    def dispatch(self, plan_id: str, *, idempotency_key: str) -> OutreachPlan:
        plan, claimed = self.store.claim_dispatch(plan_id, idempotency_key)
        if not claimed:
            return plan
        transport = self.transports.get(plan.channel)
        if transport is None:
            self.store.finish_dispatch(
                plan_id, idempotency_key, success=False, error_code="transport_unavailable"
            )
            raise LookupError("transport_unavailable")
        try:
            result = transport.send(
                destination=plan.destination, subject=plan.subject, body=plan.body,
                metadata={"plan_id": plan.plan_id, "company_id": plan.company_id,
                          "campaign_id": plan.campaign_id, "channel": plan.channel.value},
            )
            if result.get("accepted") is not True:
                code = str(result.get("error") or "provider_rejected")
                self.store.finish_dispatch(
                    plan_id, idempotency_key, success=False, error_code=code
                )
                raise RuntimeError(code)
            return self.store.finish_dispatch(
                plan_id, idempotency_key, success=True,
                provider_id=str(result.get("provider_id") or "") or None,
            )
        except Exception:
            # A transport exception is not proof of delivery. Keep it failed and auditable.
            current = self.store.get_plan(plan_id)
            if current.status == PlanStatus.SENDING:
                self.store.finish_dispatch(
                    plan_id, idempotency_key, success=False, error_code="transport_exception"
                )
            raise


class WebhookOutreachTransport:
    """Provider-neutral outbound relay; relay owns WhatsApp/voice/form vendor details."""

    def __init__(self, endpoint: str, token: str, *, timeout_seconds: int = 15) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("outreach_webhook_requires_https")
        if not token.strip():
            raise ValueError("outreach_webhook_token_required")
        self.endpoint = endpoint
        self.token = token
        self.timeout_seconds = max(1, min(int(timeout_seconds), 60))

    def send(self, *, destination: str, subject: str | None, body: str,
             metadata: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = json.dumps({
            "destination": destination, "subject": subject, "body": body,
            "metadata": dict(metadata),
        }).encode("utf-8")
        request = Request(
            self.endpoint, data=payload, method="POST",
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status < 200 or response.status >= 300:
                    return {"accepted": False, "error": f"http_{response.status}"}
                result = json.loads(response.read(65536).decode("utf-8"))
                if not isinstance(result, dict):
                    return {"accepted": False, "error": "invalid_provider_response"}
                return result
        except HTTPError as exc:
            return {"accepted": False, "error": f"http_{exc.code}"}
        except (URLError, TimeoutError, json.JSONDecodeError):
            return {"accepted": False, "error": "provider_unreachable"}


def build_webhook_transports_from_env() -> dict[Channel, WebhookOutreachTransport]:
    """Load only explicitly configured HTTPS relays; never guess provider credentials."""
    transports: dict[Channel, WebhookOutreachTransport] = {}
    for channel in Channel:
        prefix = f"JARVIS_OUTREACH_{channel.value.upper()}"
        endpoint = os.getenv(f"{prefix}_WEBHOOK_URL", "").strip()
        token = os.getenv(f"{prefix}_WEBHOOK_TOKEN", "").strip()
        if endpoint and token:
            transports[channel] = WebhookOutreachTransport(endpoint, token)
    return transports
