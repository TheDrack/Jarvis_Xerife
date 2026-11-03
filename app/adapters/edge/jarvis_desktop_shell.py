"""Native Windows shell for the shared Jarvis cloud HUD."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

DEFAULT_CLOUD_URL = "https://jarvis-api-c47i.onrender.com"
PAGES = {"home": "/", "intelligence": "/intelligence", "network": "/network-devices"}


def normalize_cloud_url(value: str) -> str:
    """Validate and normalize a Jarvis origin without accepting URL tricks."""
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
    """Build one of the explicitly supported Jarvis pages."""
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis Desktop — interface nativa conectada ao gateway remoto.")
    parser.add_argument("--base-url", default=os.environ.get("JARVIS_CLOUD_BASE_URL", DEFAULT_CLOUD_URL))
    parser.add_argument("--page", choices=tuple(PAGES), default="home")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    try:
        start_url = build_start_url(args.base_url, args.page)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        import webview
    except ImportError:
        print("Dependência ausente: instale com python -m pip install -r requirements/desktop.txt.", file=sys.stderr)
        return 2
    webview.create_window(
        "JARVIS · Desktop",
        url=start_url,
        width=1440,
        height=900,
        min_size=(960, 640),
        resizable=True,
        text_select=True,
        background_color="#070b13",
    )
    try:
        webview.start(
            gui="edgechromium",
            debug=args.debug,
            private_mode=False,
            storage_path=str(_storage_path()),
        )
    except Exception as exc:
        print(
            "Não foi possível iniciar o WebView2. Verifique a instalação do Microsoft Edge WebView2 Runtime. "
            f"Detalhe: {exc}",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
