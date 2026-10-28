"""Persistent navigation graph and adaptive route planner for Jarvis.

States and transitions are backend-independent: DOM, UI Automation, visual
templates, keyboard, or API. Callers must only record success after verifying
the destination postcondition.
"""
from __future__ import annotations

import heapq
import json
import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RouteStep:
    source: str
    target: str
    action: str
    backend: str
    expected_cost: float
    success_rate: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Route:
    source: str
    target: str
    steps: tuple[RouteStep, ...]
    total_cost: float

    @property
    def nodes(self) -> tuple[str, ...]:
        return (self.source, *(step.target for step in self.steps))


class NavigationGraph:
    """SQLite-backed graph whose edge costs improve from verified outcomes."""

    def __init__(self, database: str | Path = ":memory:", *, reliability_penalty: float = 2.0) -> None:
        if not math.isfinite(reliability_penalty) or reliability_penalty < 0:
            raise ValueError("reliability_penalty must be finite and >= 0")
        self.reliability_penalty = float(reliability_penalty)
        self._connection = sqlite3.connect(str(database), timeout=10)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        if str(database) != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS navigation_nodes (
                node_id TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT '',
                state_signature TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS navigation_edges (
                source TEXT NOT NULL REFERENCES navigation_nodes(node_id) ON DELETE CASCADE,
                target TEXT NOT NULL REFERENCES navigation_nodes(node_id) ON DELETE CASCADE,
                action TEXT NOT NULL, backend TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
                attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                successes INTEGER NOT NULL DEFAULT 0 CHECK (successes >= 0),
                failures INTEGER NOT NULL DEFAULT 0 CHECK (failures >= 0),
                mean_latency REAL NOT NULL DEFAULT 1.0 CHECK (mean_latency >= 0),
                last_latency REAL, updated_at REAL NOT NULL,
                PRIMARY KEY (source, target, action, backend)
            );
            CREATE INDEX IF NOT EXISTS idx_navigation_edges_source ON navigation_edges(source);
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def upsert_node(self, node_id: str, *, label: str = "", state_signature: str = "",
                    metadata: dict[str, Any] | None = None) -> None:
        node_id = self._validate_id(node_id)
        self._connection.execute(
            """INSERT INTO navigation_nodes(node_id,label,state_signature,metadata_json,updated_at)
               VALUES(?,?,?,?,?) ON CONFLICT(node_id) DO UPDATE SET
               label=excluded.label, state_signature=excluded.state_signature,
               metadata_json=excluded.metadata_json, updated_at=excluded.updated_at""",
            (node_id, label, state_signature, self._json(metadata or {}), time.time()),
        )
        self._connection.commit()

    def record_transition(self, source: str, target: str, *, action: str, backend: str,
                          latency_seconds: float, success: bool,
                          metadata: dict[str, Any] | None = None, alpha: float = 0.25) -> None:
        """Record one observed outcome; success means its postcondition was verified."""
        source, target = self._validate_id(source), self._validate_id(target)
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action must be a non-empty string")
        if not isinstance(backend, str) or not backend.strip():
            raise ValueError("backend must be a non-empty string")
        if not math.isfinite(latency_seconds) or latency_seconds < 0:
            raise ValueError("latency_seconds must be a finite non-negative number")
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        if not isinstance(success, bool):
            raise ValueError("success must be a bool")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be a dictionary")
        self.upsert_node(source)
        self.upsert_node(target)
        row = self._connection.execute(
            """SELECT attempts, successes, failures, mean_latency, metadata_json
               FROM navigation_edges WHERE source=? AND target=? AND action=? AND backend=?""",
            (source, target, action, backend),
        ).fetchone()
        if row is None:
            attempts, successes, failures, mean_latency = 0, 0, 0, latency_seconds
            stored_metadata = {}
        else:
            attempts, successes, failures = int(row["attempts"]), int(row["successes"]), int(row["failures"])
            mean_latency = alpha * latency_seconds + (1 - alpha) * float(row["mean_latency"])
            stored_metadata = json.loads(row["metadata_json"])
        # Keep last known useful metadata when a later observation has none.
        if metadata:
            stored_metadata.update(metadata)
        attempts += 1
        successes += int(success)
        failures += int(not success)
        self._connection.execute(
            """INSERT INTO navigation_edges
               (source,target,action,backend,metadata_json,attempts,successes,failures,
                mean_latency,last_latency,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source,target,action,backend) DO UPDATE SET
               metadata_json=excluded.metadata_json, attempts=excluded.attempts,
               successes=excluded.successes, failures=excluded.failures,
               mean_latency=excluded.mean_latency, last_latency=excluded.last_latency,
               updated_at=excluded.updated_at""",
            (source, target, action, backend, self._json(stored_metadata), attempts,
             successes, failures, mean_latency, latency_seconds, time.time()),
        )
        self._connection.commit()

    def plan(self, source: str, target: str) -> Route | None:
        """Find a minimum expected-cost route with Dijkstra's algorithm."""
        source, target = self._validate_id(source), self._validate_id(target)
        nodes = {row["node_id"] for row in self._connection.execute("SELECT node_id FROM navigation_nodes")}
        if source not in nodes or target not in nodes:
            return None
        if source == target:
            return Route(source, target, (), 0.0)
        adjacency: dict[str, list[RouteStep]] = {}
        rows = self._connection.execute("SELECT * FROM navigation_edges WHERE attempts > 0").fetchall()
        for row in rows:
            attempts, successes = int(row["attempts"]), int(row["successes"])
            success_rate = (successes + 1) / (attempts + 2)
            latency = float(row["mean_latency"])
            cost = latency + self.reliability_penalty * (1 - success_rate) / max(success_rate, 0.05)
            adjacency.setdefault(row["source"], []).append(RouteStep(
                source=row["source"], target=row["target"], action=row["action"],
                backend=row["backend"], expected_cost=cost, success_rate=success_rate,
                metadata=json.loads(row["metadata_json"]),
            ))
        queue: list[tuple[float, str]] = [(0.0, source)]
        distances = {source: 0.0}
        previous: dict[str, RouteStep] = {}
        while queue:
            distance, current = heapq.heappop(queue)
            if distance != distances.get(current):
                continue
            if current == target:
                break
            for step in adjacency.get(current, []):
                candidate = distance + step.expected_cost
                if candidate < distances.get(step.target, math.inf):
                    distances[step.target] = candidate
                    previous[step.target] = step
                    heapq.heappush(queue, (candidate, step.target))
        if target not in distances:
            return None
        steps: list[RouteStep] = []
        cursor = target
        while cursor != source:
            step = previous[cursor]
            steps.append(step)
            cursor = step.source
        steps.reverse()
        return Route(source, target, tuple(steps), distances[target])

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable graph summary for diagnostics."""
        nodes = []
        for row in self._connection.execute(
            "SELECT node_id,label,state_signature,metadata_json,updated_at FROM navigation_nodes ORDER BY node_id"
        ):
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            nodes.append(item)
        edges = []
        for row in self._connection.execute("SELECT * FROM navigation_edges ORDER BY source,target,action,backend"):
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            item["success_rate"] = (item["successes"] + 1) / (item["attempts"] + 2)
            edges.append(item)
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _validate_id(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("node IDs must be strings")
        normalized = value.strip()
        if not normalized or len(normalized) > 256:
            raise ValueError("node IDs must contain 1..256 non-whitespace characters")
        return normalized

    @staticmethod
    def _json(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
