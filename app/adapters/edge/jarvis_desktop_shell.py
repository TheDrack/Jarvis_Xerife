# -*- coding: utf-8 -*-
"""Native Windows shell for Jarvis Local Core (desktop + private LAN clients)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit, urlunsplit

DEFAULT_CLOUD_URL = "https://jarvis-api-c47i.onrender.com"
PAGES = {"home": "/", "intelligence": "/intelligence", "network": "/network-devices"}


def normalize_cloud_url(value: str) -> str:
    """Validate and normalize a Jarvis remote origin without accepting URL tricks."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("A URL do Jarvis está vazia.")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"https", "http"}:
        raise ValueError("Use HTTPS para o Jarvis remoto.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("A URL precisa conter um host válido e não pode incluir credenciais.")
    if parsed.query or parsed.fragment:
        raise ValueError("A URL base não pode conter query string ou fragmento.")
    hostname = parsed.hostname.casefold()
    if parsed.scheme != "https" and hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("HTTP sem TLS só é permitido para loopback local.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Porta inválida na URL do Jarvis.") from exc
    netloc = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


def build_start_url(base_url: str, page: str = "home") -> str:
    """Build one of the explicitly supported legacy remote pages."""
    if page not in PAGES:
        raise ValueError(f"Página inválida: {page}. Opções: {', '.join(PAGES)}")
    return f"{normalize_cloud_url(base_url)}{PAGES[page]}"


def _storage_path() -> Path:
    """Persist the WebView profile per Windows user, not in the repository."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    path = root / "Jarvis" / "Desktop" / "WebView2"
    path.mkdir(parents=True, exist_ok=True)
    return path



class DesktopWindowBridge:
    """Expose only the native window operations required by the local HUD."""

    def __init__(self) -> None:
        self._window = None
        self._fullscreen = False
        self._lock = Lock()

    def bind_window(self, window) -> None:
        self._window = window

    def set_fullscreen(self, enabled: bool) -> bool:
        with self._lock:
            if self._window is None:
                raise RuntimeError("A janela nativa do Jarvis ainda não foi inicializada.")
            desired = bool(enabled)
            if desired != self._fullscreen:
                self._window.toggle_fullscreen()
                self._fullscreen = desired
            return self._fullscreen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis Desktop — núcleo local com acesso opcional pela LAN.")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--loopback-only", action="store_true",
                        help="Restringe o painel ao próprio PC; desativa acesso Android pela LAN.")
    parser.add_argument(
        "--remote-url", "--base-url", dest="remote_url",
        default=os.environ.get("JARVIS_CLOUD_BASE_URL", ""),
        help="Abre explicitamente o HUD remoto legado em vez do núcleo local.",
    )
    parser.add_argument("--page", choices=tuple(PAGES), default="home")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("--port deve estar entre 1024 e 65535.")
    try:
        import webview
    except ImportError:
        print("Dependência ausente: instale com python -m pip install -r requirements/desktop.txt.", file=sys.stderr)
        return 2

    server = None
    window_bridge = DesktopWindowBridge()
    try:
        if args.remote_url:
            start_url = build_start_url(args.remote_url, args.page)
        else:
            from app.adapters.edge.jarvis_desktop_local import run_local_server
            host = "127.0.0.1" if args.loopback_only else "0.0.0.0"
            server, _thread = run_local_server(host=host, port=args.port)
            start_url = f"http://127.0.0.1:{args.port}/"
        window = webview.create_window(
            "JARVIS · Desktop",
            url=start_url,
            js_api=None if args.remote_url else window_bridge,
            width=1500,
            height=940,
            min_size=(1024, 680),
            resizable=True,
            text_select=True,
            background_color="#07111d",
        )
        if not args.remote_url:
            window_bridge.bind_window(window)
        webview.start(
            gui="edgechromium",
            debug=args.debug,
            private_mode=False,
            storage_path=str(_storage_path()),
        )
        return 0
    except Exception as exc:
        print(f"Falha ao iniciar Jarvis Desktop: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    finally:
        if server is not None:
            server.should_exit = True


if __name__ == "__main__":
    raise SystemExit(main())