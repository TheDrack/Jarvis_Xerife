"""Process-level supervisor for the Termux task-queue worker.

Reuses the existing queue and worker runtime. Keeps the process alive for runit,
restarts an exited worker thread, handles SIGTERM/SIGINT, and writes secret-free
health state. It does not create another queue or task store.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .agent_worker_runtime import start_configured_worker

logger = logging.getLogger(__name__)
DEFAULT_MONITOR_INTERVAL_SECONDS = 5.0
DEFAULT_STATUS_INTERVAL_SECONDS = 30.0
DEFAULT_RESTART_MIN_BACKOFF_SECONDS = 2.0
DEFAULT_RESTART_MAX_BACKOFF_SECONDS = 60.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 60.0
WorkerRuntimeFactory = Callable[[], tuple[Any, Any] | None]


def default_status_path() -> Path:
    configured = os.getenv("JARVIS_WORKER_STATUS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    home = Path(os.getenv("HOME", str(Path.home())))
    return home / "jarvis-mobile" / "state" / "agent-worker.status"


@contextmanager
def acquire_instance_lock(path: str | Path) -> Iterator[None]:
    """Prevent two independent daemon processes from consuming as one host."""
    lock_path = Path(path).expanduser()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    unlock: Callable[[], None]
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write("\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("another Jarvis worker daemon already owns the lock") from exc
            unlock = lambda: (handle.seek(0), msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1))
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("another Jarvis worker daemon already owns the lock") from exc
            unlock = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        yield
    finally:
        try:
            if "unlock" in locals():
                unlock()
        finally:
            handle.close()


class WorkerDaemon:
    """Keep exactly one Termux worker slot alive under an external supervisor."""

    def __init__(
        self,
        *,
        start_worker: WorkerRuntimeFactory | None = None,
        status_path: str | Path | None = None,
        stop_event: threading.Event | None = None,
        monitor_interval_seconds: float = DEFAULT_MONITOR_INTERVAL_SECONDS,
        status_interval_seconds: float = DEFAULT_STATUS_INTERVAL_SECONDS,
        restart_min_backoff_seconds: float = DEFAULT_RESTART_MIN_BACKOFF_SECONDS,
        restart_max_backoff_seconds: float = DEFAULT_RESTART_MAX_BACKOFF_SECONDS,
        shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
    ) -> None:
        if monitor_interval_seconds <= 0:
            raise ValueError("monitor_interval_seconds must be positive")
        if status_interval_seconds <= 0:
            raise ValueError("status_interval_seconds must be positive")
        if restart_min_backoff_seconds <= 0:
            raise ValueError("restart_min_backoff_seconds must be positive")
        if restart_max_backoff_seconds < restart_min_backoff_seconds:
            raise ValueError("restart_max_backoff_seconds must be >= minimum backoff")
        if shutdown_timeout_seconds <= 0:
            raise ValueError("shutdown_timeout_seconds must be positive")
        self.start_worker = start_worker or start_configured_worker
        self.status_path = Path(status_path) if status_path is not None else default_status_path()
        self.stop_event = stop_event or threading.Event()
        self.monitor_interval_seconds = monitor_interval_seconds
        self.status_interval_seconds = status_interval_seconds
        self.restart_min_backoff_seconds = restart_min_backoff_seconds
        self.restart_max_backoff_seconds = restart_max_backoff_seconds
        self.shutdown_timeout_seconds = shutdown_timeout_seconds
        self.restart_count = 0
        self.last_error_type: str | None = None
        self.worker_id: str | None = None

    def _write_status(self, status: str) -> None:
        """Atomically publish state without exception text or credentials."""
        payload = {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "epoch": time.time(),
            "pid": os.getpid(),
            "worker_id": self.worker_id,
            "restart_count": self.restart_count,
            "last_error_type": self.last_error_type,
        }
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.status_path.with_name(f"{self.status_path.name}.{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.status_path)
            os.chmod(self.status_path, 0o600)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)

    def _stop_runtime(self, group: Any, worker_stop: Any) -> None:
        if worker_stop is not None:
            worker_stop.set()
        if group is not None:
            group.join(timeout=self.shutdown_timeout_seconds)
            if group.is_alive():
                logger.error("Worker did not stop within the configured shutdown timeout")

    def run(self) -> int:
        """Run until stopped; restart failed startup or an exited worker thread."""
        backoff = self.restart_min_backoff_seconds
        self._write_status("starting")
        try:
            while not self.stop_event.is_set():
                group = None
                worker_stop = None
                try:
                    runtime = self.start_worker()
                    if runtime is None:
                        raise RuntimeError(
                            "mini-agent runtime is disabled; set JARVIS_MINI_AGENT_ENABLED=true"
                        )
                    group, worker_stop = runtime
                    threads = tuple(getattr(group, "threads", ()))
                    if len(threads) != 1:
                        self._stop_runtime(group, worker_stop)
                        group = None
                        worker_stop = None
                        raise RuntimeError(
                            "Termux worker daemon requires exactly one configured worker slot"
                        )

                    self.worker_id = getattr(threads[0], "name", "jarvis-termux-worker")
                    self.last_error_type = None
                    stable_since = time.monotonic()
                    logger.info("Termux worker daemon active (worker_id=%s)", self.worker_id)
                    self._write_status("running")
                    next_status_update = time.monotonic() + self.status_interval_seconds

                    while not self.stop_event.wait(self.monitor_interval_seconds):
                        if not group.is_alive():
                            raise RuntimeError("worker thread exited unexpectedly")
                        now = time.monotonic()
                        if now - stable_since >= 300:
                            backoff = self.restart_min_backoff_seconds
                            stable_since = now
                        if now >= next_status_update:
                            self._write_status("running")
                            next_status_update = now + self.status_interval_seconds

                    self._stop_runtime(group, worker_stop)
                    group = None
                    worker_stop = None
                    break
                except Exception as exc:  # noqa: BLE001 - process supervision boundary
                    self._stop_runtime(group, worker_stop)
                    self.restart_count += 1
                    self.last_error_type = type(exc).__name__
                    logger.error(
                        "Worker startup/runtime failed; retrying with bounded backoff "
                        "(error_type=%s, backoff_seconds=%.1f)",
                        self.last_error_type,
                        backoff,
                    )
                    self._write_status("degraded")
                    if self.stop_event.wait(backoff):
                        break
                    backoff = min(self.restart_max_backoff_seconds, backoff * 2)
        finally:
            self._write_status("stopped")
        return 0


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis Termux continuous worker daemon")
    parser.add_argument("--status-file", type=Path, default=default_status_path())
    parser.add_argument("--lock-file", type=Path)
    parser.add_argument(
        "--monitor-interval", type=_positive_float,
        default=float(os.getenv("JARVIS_WORKER_MONITOR_INTERVAL_SECONDS", DEFAULT_MONITOR_INTERVAL_SECONDS)),
    )
    parser.add_argument(
        "--restart-min-backoff", type=_positive_float,
        default=float(os.getenv("JARVIS_WORKER_RESTART_MIN_BACKOFF_SECONDS", DEFAULT_RESTART_MIN_BACKOFF_SECONDS)),
    )
    parser.add_argument(
        "--restart-max-backoff", type=_positive_float,
        default=float(os.getenv("JARVIS_WORKER_RESTART_MAX_BACKOFF_SECONDS", DEFAULT_RESTART_MAX_BACKOFF_SECONDS)),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=os.getenv("JARVIS_WORKER_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stop_event = threading.Event()

    def request_shutdown(signum: int, _frame: Any) -> None:
        logger.info("Received signal %s; requesting graceful worker shutdown", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    lock_path = args.lock_file or args.status_file.with_suffix(args.status_file.suffix + ".lock")
    try:
        with acquire_instance_lock(lock_path):
            daemon = WorkerDaemon(
                status_path=args.status_file,
                stop_event=stop_event,
                monitor_interval_seconds=args.monitor_interval,
                status_interval_seconds=float(os.getenv("JARVIS_WORKER_STATUS_INTERVAL_SECONDS", DEFAULT_STATUS_INTERVAL_SECONDS)),
                restart_min_backoff_seconds=args.restart_min_backoff,
                restart_max_backoff_seconds=args.restart_max_backoff,
            )
            return daemon.run()
    except RuntimeError as exc:
        logger.error("Worker daemon refused to start (%s)", type(exc).__name__)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
