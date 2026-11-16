"""Versioned registry of sanitized, observed application protocol patterns."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_SENSITIVE = re.compile(r"(pass(word)?|passwd|token|secret|auth(orization)?|cookie|api.?key|credential|session)", re.I)
_EVIDENCE_SECRET = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*|((?:token|secret|password|authorization|cookie|api[_-]?key)\s*[:=]\s*)[^\s,;&]+")
_DYNAMIC_PATH_SEGMENT = re.compile(r"^(?:[0-9]{4,}|[0-9a-f]{24,}|[A-Za-z0-9_-]{32,}|[0-9a-f]{8}-[0-9a-f-]{27,})$", re.I)
_ALLOWED_STATUSES = {"observed", "validated", "reusable"}
_ALLOWED_TRANSITIONS = {"observed": {"validated"}, "validated": {"reusable"}, "reusable": set()}


def _field_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _body_schema(value: Any, depth: int = 0) -> Any:
    """Extract field/type shape without retaining application data values."""
    if depth >= 6:
        return "object"
    if isinstance(value, dict):
        return {
            str(key)[:128]: "redacted" if _SENSITIVE.search(str(key)) else _body_schema(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return {"items": _body_schema(value[0], depth + 1)} if value else {"items": "unknown"}
    return _field_type(value)


def _safe_url(raw_url: Any) -> dict[str, str]:
    try:
        parsed = urlsplit(str(raw_url or ""))
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        segments = ["[ID]" if _DYNAMIC_PATH_SEGMENT.fullmatch(part) else part for part in (parsed.path or "/").split("/")]
        safe_path = "/".join(segments)
        return {"scheme": parsed.scheme.lower()[:16], "host": host[:255], "path": safe_path[:1024]}
    except (TypeError, ValueError):
        return {"scheme": "", "host": "", "path": ""}


def _content_type(headers: Any) -> str | None:
    if not isinstance(headers, dict):
        return None
    value = next((v for k, v in headers.items() if str(k).lower() == "content-type"), None)
    return str(value).split(";", 1)[0].strip().lower()[:128] if value else None


def _safe_evidence(value: str) -> str:
    return _EVIDENCE_SECRET.sub("[REDACTED]", str(value))[:240]


class ProtocolPatternRegistry:
    """Append-only JSONL registry with explicit knowledge-state transitions."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).expanduser()
        self.path = self.directory / "protocol-patterns.jsonl"
        self._lock = threading.RLock()

    @staticmethod
    def _build_pattern(observation: dict[str, Any]) -> dict[str, Any]:
        request = observation.get("request") if isinstance(observation.get("request"), dict) else observation
        response = observation.get("response") if isinstance(observation.get("response"), dict) else {}
        endpoint = _safe_url(request.get("url", observation.get("url", "")))
        request_headers = request.get("headers", observation.get("request_headers", {}))
        response_headers = response.get("headers", observation.get("response_headers", {}))
        request_body = request.get("body", observation.get("request_body"))
        response_body = response.get("body")
        pattern: dict[str, Any] = {
            "transport": str(observation.get("transport") or endpoint["scheme"] or "unknown")[:32],
            "request": {
                "method": str(request.get("method", observation.get("method", "UNKNOWN"))).upper()[:16],
                **endpoint,
                "content_type": _content_type(request_headers),
            },
            "response": {"status": response.get("status", observation.get("status")), "content_type": _content_type(response_headers)},
        }
        if request_body is not None:
            pattern["request"]["body_schema"] = _body_schema(request_body)
        if response_body is not None:
            pattern["response"]["body_schema"] = _body_schema(response_body)
        sequence = observation.get("sequence")
        if isinstance(sequence, list):
            pattern["sequence"] = [str(item)[:80] for item in sequence[:64]]
        return pattern

    def _read_latest(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        if not self.path.exists():
            return latest
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(record, dict) and isinstance(record.get("id"), str):
                    latest[record["id"]] = record
        return latest

    def _append(self, record: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.directory, 0o700)
        except OSError:
            pass
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def record_observation(self, *, package: str, app_version: str, operation: str, observation: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(package, str) or not package.strip() or len(package) > 255:
            raise ValueError("package must be a non-empty package identifier")
        if not isinstance(app_version, str) or not app_version.strip() or len(app_version) > 80:
            raise ValueError("app_version must be a non-empty version")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 128:
            raise ValueError("operation must be a non-empty operation identifier")
        if not isinstance(observation, dict):
            raise ValueError("observation must be a structured object")
        record = {
            "id": uuid.uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "package": package.strip(),
            "app_version": app_version.strip(),
            "operation": operation.strip(),
            "status": "observed",
            "pattern": self._build_pattern(observation),
        }
        with self._lock:
            self._append(record)
        return record

    def record_flow_observations(
        self, *, package: str, app_version: str, flows: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Import passive Android flow metadata only when attribution is unambiguous.

        This records observed hostname-to-app associations, not HTTP transactions
        or replayable API contracts. Shared-UID and unresolved flows are skipped.
        """
        if not isinstance(package, str) or not package.strip() or len(package) > 255:
            raise ValueError("package must be a non-empty package identifier")
        if not isinstance(app_version, str) or not app_version.strip() or len(app_version) > 80:
            raise ValueError("app_version must be a non-empty version")
        if not isinstance(flows, list) or len(flows) > 50:
            raise ValueError("flows must be a list containing at most 50 entries")

        skipped_unattributed = 0
        pending_records: list[dict[str, Any]] = []
        expected_sources = {
            "dns_query": "dns",
            "dns_response_question": "dns",
            "http_host": "http",
            "tls_sni": "tls_client_hello",
        }
        for flow in flows:
            if not isinstance(flow, dict):
                raise ValueError("flow entry must be an object")
            packages = flow.get("package_names", [])
            if flow.get("attribution_status") != "resolved" or packages != [package]:
                skipped_unattributed += 1
                continue

            transport = flow.get("protocol")
            remote_ip = flow.get("remote_ip")
            remote_port = flow.get("remote_port")
            if transport not in {"tcp", "udp"}:
                raise ValueError("flow transport must be tcp or udp")
            try:
                remote_ip = str(ipaddress.ip_address(remote_ip))
            except (TypeError, ValueError):
                raise ValueError("flow remote_ip must be a valid IP address") from None
            if isinstance(remote_port, bool) or not isinstance(remote_port, int) or not 0 <= remote_port <= 65535:
                raise ValueError("flow remote_port must be an integer from 0 to 65535")

            observations = flow.get("protocol_observations", [])
            if not isinstance(observations, list) or len(observations) > 3:
                raise ValueError("flow protocol_observations must contain at most 3 entries")
            for observation in observations:
                if not isinstance(observation, dict) or set(observation) != {"kind", "value", "source"}:
                    raise ValueError("protocol observation schema is invalid")
                kind, hostname, source = (
                    observation.get("kind"), observation.get("value"), observation.get("source")
                )
                if kind not in expected_sources or source != expected_sources[kind]:
                    raise ValueError("protocol observation kind/source is invalid")
                if not isinstance(hostname, str) or hostname != hostname.lower() or len(hostname) > 253:
                    raise ValueError("protocol observation hostname is invalid")
                labels = hostname.split(".")
                if any(
                    not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
                    or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in label)
                    for label in labels
                ):
                    raise ValueError("protocol observation hostname is invalid")

                network_pattern = {
                    "kind": kind,
                    "hostname": hostname,
                    "source": source,
                    "transport": transport,
                    "remote_ip": remote_ip,
                    "remote_port": remote_port,
                    "first_seen_at": str(flow.get("first_seen_at") or "")[:40],
                    "attribution": "uniquely_resolved",
                }
                identity_pattern = {
                    key: value for key, value in network_pattern.items() if key != "first_seen_at"
                }
                identity = json.dumps(
                    [package.strip(), app_version.strip(), identity_pattern],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                pattern_id = "net_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
                pending_records.append({
                    "id": pattern_id,
                    "created_at": datetime.now(UTC).isoformat(),
                    "package": package.strip(),
                    "app_version": app_version.strip(),
                    "operation": kind,
                    "status": "observed",
                    "source": "android_vpn_passive_metadata",
                    "confidence": "observed",
                    "network_pattern": network_pattern,
                })

        recorded = 0
        already_known = 0
        with self._lock:
            known_ids = set(self._read_latest())
            for record in pending_records:
                if record["id"] in known_ids:
                    already_known += 1
                    continue
                self._append(record)
                known_ids.add(record["id"])
                recorded += 1
        return {
            "recorded": recorded,
            "skipped_unattributed": skipped_unattributed,
            "already_known": already_known,
        }

    def list_patterns(self, *, package: str | None = None, operation: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._read_latest().values())
        if package is not None:
            records = [item for item in records if item["package"] == package]
        if operation is not None:
            records = [item for item in records if item["operation"] == operation]
        return sorted(records, key=lambda item: item["created_at"])

    def transition(self, pattern_id: str, status: str, *, evidence: str = "") -> dict[str, Any]:
        if status not in _ALLOWED_STATUSES:
            raise ValueError("unsupported pattern status")
        with self._lock:
            record = self._read_latest().get(pattern_id)
            if record is None:
                raise KeyError(pattern_id)
            current = record["status"]
            if status not in _ALLOWED_TRANSITIONS[current]:
                raise ValueError(f"validation required: invalid transition {current} -> {status}")
            if not str(evidence).strip():
                raise ValueError("validation evidence is required for status transition")
            updated = dict(record)
            updated["status"] = status
            updated["updated_at"] = datetime.now(UTC).isoformat()
            updated["evidence"] = _safe_evidence(evidence)
            self._append(updated)
            return updated

    def compare_versions(self, *, package: str, operation: str, older: str, newer: str) -> dict[str, Any]:
        records = self.list_patterns(package=package, operation=operation)
        old = next((item for item in records if item["app_version"] == older), None)
        new = next((item for item in records if item["app_version"] == newer), None)
        if old is None or new is None:
            raise KeyError("pattern missing for one or both app versions")

        if "network_pattern" in old or "network_pattern" in new:
            if "network_pattern" not in old or "network_pattern" not in new:
                changes = ["record_type"]
            else:
                fields = (
                    "kind", "hostname", "source", "transport", "remote_ip", "remote_port"
                )
                changes = [
                    f"network_pattern.{field}"
                    for field in fields
                    if old["network_pattern"].get(field) != new["network_pattern"].get(field)
                ]
        else:
            old_pattern, new_pattern = old["pattern"], new["pattern"]
            fields = (
                ("request", "method"), ("request", "scheme"), ("request", "host"),
                ("request", "path"), ("request", "content_type"),
                ("request", "body_schema"), ("response", "status"),
                ("response", "content_type"), ("response", "body_schema"),
                ("transport", None),
            )
            changes = []
            for section, key in fields:
                left = old_pattern.get(section) if key is None else old_pattern.get(section, {}).get(key)
                right = new_pattern.get(section) if key is None else new_pattern.get(section, {}).get(key)
                if left != right:
                    changes.append(section if key is None else f"{section}.{key}")

        return {
            "package": package,
            "operation": operation,
            "older_version": older,
            "newer_version": newer,
            "changed": bool(changes),
            "changes": changes,
        }
