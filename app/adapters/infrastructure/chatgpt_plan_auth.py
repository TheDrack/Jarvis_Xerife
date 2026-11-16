"""Local OAuth authorization for Sign in with ChatGPT open-source clients."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import webbrowser
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from jose import jwt

from app.adapters.infrastructure.chatgpt_plan_runtime import (
    PLAN_USAGE_SCOPE,
    ChatGPTPlanCredentialStore,
    ChatGPTPlanError,
)
from app.adapters.infrastructure.secure_file_permissions import (
    set_private_directory_permissions,
    set_private_file_permissions,
    verify_private_directory_permissions,
    verify_private_file_permissions,
)

ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = f"{ISSUER}/api/accounts/authorize"
TOKEN_URL = f"{ISSUER}/api/accounts/oauth/token"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
IDENTITY_SCOPES = ("openid", "profile", "email")
PLAN_SCOPES = ("offline_access", "resource.invoke", PLAN_USAGE_SCOPE)


def create_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorization_url(
    *,
    client_id: str,
    app_name: str,
    host_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_challenge: str,
    id_token_hint: str | None = None,
) -> str:
    """Build the documented open-source OAuth authorization URL."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join((*IDENTITY_SCOPES, *PLAN_SCOPES)),
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
        "ext_agent_host_id": host_id,
    }
    if client_id == "dynamic_agent_client":
        params["agent_name_hint"] = app_name
    elif id_token_hint:
        params["id_token_hint"] = id_token_hint
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


class _CallbackHandler(BaseHTTPRequestHandler):
    callback_queue: Any = None
    expected_state: str = ""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_error(404)
            return
        callback = parse_qs(parsed.query, keep_blank_values=True)
        returned_state = _first(callback, "state")
        if not returned_state or not secrets.compare_digest(
            returned_state, self.expected_state
        ):
            self.send_error(400, "Invalid OAuth state")
            return
        self.callback_queue.put(callback)
        body = (
            "<!doctype html><meta charset='utf-8'><title>Jarvis</title>"
            "<h2>Autorização recebida</h2><p>Você pode voltar ao Jarvis.</p>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: Any) -> None:
        return


class ChatGPTPlanOAuth:
    """Sign-in, refresh and identity validation for one local Jarvis runtime."""

    def __init__(
        self,
        *,
        store: ChatGPTPlanCredentialStore | None = None,
        app_name: str = "Jarvis Xerife",
        http_client: httpx.Client | None = None,
        browser_opener: Callable[[str], bool] | None = None,
        initial_callback_port: int = 1455,
    ) -> None:
        self.store = store or ChatGPTPlanCredentialStore()
        self.app_name = app_name
        self._http = http_client or httpx.Client(timeout=30.0)
        self._owns_http = http_client is None
        self._browser_opener = browser_opener or _open_system_browser
        if (
            isinstance(initial_callback_port, bool)
            or not isinstance(initial_callback_port, int)
            or not 0 <= initial_callback_port <= 65535
        ):
            raise ValueError("initial_callback_port must be a valid TCP port")
        self.initial_callback_port = initial_callback_port
        self._refresh_lock = threading.RLock()

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def sign_in(self, *, timeout_seconds: int = 300) -> dict[str, Any]:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds < 30
        ):
            raise ValueError("timeout_seconds must be an integer of at least 30")
        host_id = self._get_or_create_host_id()
        previous = self.store.load()
        client_id = (
            (previous.get("client_id") if previous else None)
            or self._load_registered_client_id()
            or "dynamic_agent_client"
        )
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        verifier, challenge = create_pkce_pair()
        callback_queue: queue.Queue = queue.Queue(maxsize=1)
        handler = type(
            "JarvisOAuthCallback",
            (_CallbackHandler,),
            {
                "callback_queue": callback_queue,
                "expected_state": state,
            },
        )
        callback_port = (
            0
            if previous or client_id != "dynamic_agent_client"
            else self.initial_callback_port
        )
        try:
            server = ThreadingHTTPServer(("127.0.0.1", callback_port), handler)
        except OSError as exc:
            raise ChatGPTPlanError(
                "The required local OAuth callback port is unavailable.",
                code="callback_port_unavailable",
            ) from exc
        server.daemon_threads = True
        server.timeout = 1.0
        redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/auth/callback"
        auth_url = build_authorization_url(
            client_id=client_id,
            app_name=self.app_name,
            host_id=host_id,
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            code_challenge=challenge,
            id_token_hint=previous.get("id_token") if previous else None,
        )
        try:
            try:
                opened = self._browser_opener(auth_url)
            except Exception as exc:
                raise ChatGPTPlanError(
                    "Unable to open the system browser for ChatGPT authorization.",
                    code="browser_not_opened",
                ) from exc
            if not opened:
                raise ChatGPTPlanError(
                    "Unable to open the system browser for ChatGPT authorization.",
                    code="browser_not_opened",
                )
            deadline = time.monotonic() + timeout_seconds
            callback = None
            while time.monotonic() < deadline:
                server.handle_request()
                try:
                    callback = callback_queue.get_nowait()
                    break
                except queue.Empty:
                    continue
            if callback is None:
                raise ChatGPTPlanError(
                    "ChatGPT authorization timed out.", code="authorization_timeout"
                )
        finally:
            server.server_close()
        return self._complete_callback(
            callback,
            state=state,
            nonce=nonce,
            verifier=verifier,
            redirect_uri=redirect_uri,
            expected_client_id=client_id,
            previous=previous,
            host_id=host_id,
        )

    def _complete_callback(
        self,
        callback: dict[str, list[str]],
        *,
        state: str,
        nonce: str,
        verifier: str,
        redirect_uri: str,
        expected_client_id: str,
        previous: dict[str, Any] | None,
        host_id: str,
    ) -> dict[str, Any]:
        returned_state = _first(callback, "state")
        if not returned_state or not secrets.compare_digest(returned_state, state):
            raise ChatGPTPlanError(
                "OAuth state validation failed.", code="invalid_state"
            )
        oauth_error = _first(callback, "error")
        if oauth_error:
            code = (
                "authorization_denied"
                if oauth_error == "access_denied"
                else "authorization_failed"
            )
            raise ChatGPTPlanError(
                "ChatGPT authorization was not completed.", code=code
            )
        code = _first(callback, "code")
        if not code:
            raise ChatGPTPlanError(
                "OAuth callback did not contain an authorization code.",
                code="invalid_callback",
            )
        issued_client_id = _first(callback, "client_id") or expected_client_id
        if expected_client_id == "dynamic_agent_client":
            if not issued_client_id or issued_client_id == "dynamic_agent_client":
                raise ChatGPTPlanError(
                    "OpenAI did not issue a registered client ID.",
                    code="registration_incomplete",
                )
        elif issued_client_id != expected_client_id:
            raise ChatGPTPlanError(
                "OAuth callback changed the selected ChatGPT registration.",
                code="client_id_mismatch",
            )
        self._save_registered_client_id(issued_client_id)
        tokens = self._token_request(
            {
                "grant_type": "authorization_code",
                "client_id": issued_client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "resource": RESOURCE,
            }
        )
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise ChatGPTPlanError(
                "ChatGPT token response omitted the identity token.",
                code="invalid_id_token",
            )
        identity = self._verify_identity(id_token, issued_client_id, nonce=nonce)
        token_type = tokens.get("token_type", "Bearer")
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise ChatGPTPlanError(
                "ChatGPT returned an unsupported token type.",
                code="invalid_token_response",
            )
        scopes = _scopes(tokens.get("scope"))
        if not {PLAN_USAGE_SCOPE, "resource.invoke"}.issubset(scopes):
            raise ChatGPTPlanError(
                "ChatGPT plan-usage permission was not granted.",
                code="plan_permission_missing",
            )
        now = time.time()
        profile = {
            "client_id": issued_client_id,
            "subject": identity["sub"],
            "issuer": ISSUER,
            "email": identity.get("email"),
            "id_token": id_token,
            "access_token": _required_token(tokens, "access_token"),
            "refresh_token": _required_token(tokens, "refresh_token"),
            "token_type": token_type,
            "scopes": sorted(scopes),
            "expires_at": now + _expires_in(tokens),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "ext_agent_host_id": host_id,
        }
        self.store.save(profile)
        return {
            "connected": True,
            "email": profile["email"],
            "plan_usage_enabled": True,
            "client_id": issued_client_id,
        }

    def load_valid_profile(self, *, refresh_margin_seconds: int = 60) -> dict[str, Any]:
        with self._refresh_lock, self._exclusive_refresh_file_lock():
            profile = self.store.load()
            if not profile:
                raise ChatGPTPlanError(
                    "ChatGPT is not connected. Run the local sign-in flow.",
                    code="not_connected",
                )
            for key in ("client_id", "subject", "access_token", "refresh_token"):
                if not isinstance(profile.get(key), str) or not profile[key].strip():
                    raise ChatGPTPlanError(
                        "The local ChatGPT profile is incomplete; sign in again.",
                        code="credential_store_error",
                    )
            scopes = profile.get("scopes")
            if not isinstance(scopes, (list, tuple, set)):
                raise ChatGPTPlanError(
                    "The local ChatGPT profile has invalid permissions metadata.",
                    code="credential_store_error",
                )
            required = {PLAN_USAGE_SCOPE, "resource.invoke"}
            if not required.issubset(set(scopes)):
                raise ChatGPTPlanError(
                    "ChatGPT plan-usage permission is missing.",
                    code="plan_permission_missing",
                )
            expires_at = profile.get("expires_at")
            if (
                not isinstance(expires_at, (int, float))
                or expires_at <= time.time() + refresh_margin_seconds
            ):
                profile = self._refresh(profile)
                self.store.save(profile)
            return profile

    def get_access_token(self) -> str:
        return self.load_valid_profile()["access_token"]

    @contextmanager
    def _exclusive_refresh_file_lock(self):
        """Serialize rotating refresh-token use across Jarvis processes."""
        lock_path = self.store.path.with_name(self.store.path.name + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        set_private_directory_permissions(lock_path.parent)
        if lock_path.is_symlink():
            raise PermissionError("ChatGPT refresh lock must not be a symbolic link")
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            created = True
        except FileExistsError:
            fd = os.open(lock_path, os.O_RDWR)
            created = False
        try:
            if created:
                set_private_file_permissions(lock_path)
            else:
                verify_private_file_permissions(lock_path)
        except Exception:
            os.close(fd)
            raise
        try:
            try:
                import fcntl
            except ImportError:
                fcntl = None
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            else:
                import msvcrt

                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)

    def _refresh(self, profile: dict[str, Any]) -> dict[str, Any]:
        refresh_token = profile.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ChatGPTPlanError(
                "ChatGPT connection must be authorized again.",
                code="reauthorization_required",
            )
        tokens = self._token_request(
            {
                "grant_type": "refresh_token",
                "client_id": profile["client_id"],
                "refresh_token": refresh_token,
                "resource": RESOURCE,
            }
        )
        scopes = _scopes(tokens.get("scope")) or set(profile.get("scopes", []))
        if not {PLAN_USAGE_SCOPE, "resource.invoke"}.issubset(scopes):
            raise ChatGPTPlanError(
                "ChatGPT plan-usage permission is no longer available.",
                code="plan_permission_missing",
            )
        id_token = tokens.get("id_token") or profile.get("id_token")
        identity = None
        if tokens.get("id_token"):
            identity = self._verify_identity(id_token, profile["client_id"])
            if identity.get("sub") != profile.get("subject"):
                raise ChatGPTPlanError(
                    "Refreshed ChatGPT identity does not match the saved profile.",
                    code="identity_mismatch",
                )
        token_type = tokens.get("token_type", profile.get("token_type", "Bearer"))
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise ChatGPTPlanError(
                "ChatGPT returned an unsupported token type.",
                code="invalid_token_response",
            )
        updated = dict(profile)
        updated.update(
            {
                "access_token": _required_token(tokens, "access_token"),
                "refresh_token": tokens.get("refresh_token") or refresh_token,
                "id_token": id_token,
                "token_type": token_type,
                "email": (
                    identity.get("email", profile.get("email"))
                    if identity
                    else profile.get("email")
                ),
                "scopes": sorted(scopes),
                "expires_at": time.time() + _expires_in(tokens),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return updated

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._http.post(
                TOKEN_URL, data=form, headers={"Accept": "application/json"}
            )
        except httpx.TimeoutException as exc:
            raise ChatGPTPlanError(
                "ChatGPT authorization request timed out.", code="oauth_timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise ChatGPTPlanError(
                "ChatGPT authorization service is unreachable.",
                code="oauth_transport_error",
                retryable=True,
            ) from exc
        if response.is_error:
            status = response.status_code
            provider_error = None
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = None
            if isinstance(error_payload, dict):
                candidate = error_payload.get("error")
                if isinstance(candidate, str) and re.fullmatch(
                    r"[A-Za-z0-9_.-]{1,64}", candidate
                ):
                    provider_error = candidate
            if provider_error:
                code = f"oauth_{provider_error}"
                detail = provider_error
            elif status in {400, 401}:
                code = "reauthorization_required"
                detail = f"HTTP_{status}"
            else:
                code = "oauth_failed"
                detail = f"HTTP_{status}"
            raise ChatGPTPlanError(
                f"ChatGPT token exchange failed ({detail}).",
                code=code,
                retryable=status >= 500,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ChatGPTPlanError(
                "ChatGPT token endpoint returned invalid JSON.",
                code="invalid_token_response",
            ) from exc
        if not isinstance(payload, dict):
            raise ChatGPTPlanError(
                "ChatGPT token endpoint returned an invalid response.",
                code="invalid_token_response",
            )
        return payload

    def _verify_identity(
        self, token: str, client_id: str, nonce: str | None = None
    ) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            kid, algorithm = header.get("kid"), header.get("alg")
            if not isinstance(kid, str) or algorithm not in {"RS256", "ES256"}:
                raise ValueError("unsupported signing key")
            jwks = self._load_jwks()
            key = next(
                (
                    item
                    for item in jwks.get("keys", [])
                    if isinstance(item, dict) and item.get("kid") == kid
                ),
                None,
            )
            if key is None:
                self._jwks_cache = None
                jwks = self._load_jwks()
                key = next(
                    (
                        item
                        for item in jwks.get("keys", [])
                        if isinstance(item, dict) and item.get("kid") == kid
                    ),
                    None,
                )
            if key is None:
                raise ValueError("signing key not found")
            claims = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=client_id,
                issuer=ISSUER,
                options={"verify_at_hash": False},
            )
            if not isinstance(claims.get("sub"), str) or not claims["sub"]:
                raise ValueError("missing subject")
            if nonce is not None and not secrets.compare_digest(
                str(claims.get("nonce", "")), nonce
            ):
                raise ValueError("nonce mismatch")
            return claims
        except Exception as exc:
            raise ChatGPTPlanError(
                "ChatGPT identity token validation failed.", code="invalid_id_token"
            ) from exc

    def _load_jwks(self) -> dict[str, Any]:
        cached = getattr(self, "_jwks_cache", None)
        cached_at = getattr(self, "_jwks_cached_at", 0.0)
        if isinstance(cached, dict) and time.time() - cached_at < 3600:
            return cached
        try:
            response = self._http.get(JWKS_URL, headers={"Accept": "application/json"})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ChatGPTPlanError(
                "Unable to retrieve ChatGPT identity signing keys.",
                code="jwks_unavailable",
                retryable=True,
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise ChatGPTPlanError(
                "ChatGPT identity signing keys are malformed.", code="invalid_jwks"
            )
        self._jwks_cache, self._jwks_cached_at = payload, time.time()
        return payload

    def _get_or_create_host_id(self) -> str:
        parent = self.store.path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent.is_symlink():
            raise ChatGPTPlanError(
                "ChatGPT credential directory is unsafe.", code="unsafe_storage"
            )
        set_private_directory_permissions(parent)
        path = parent / "host-id"
        if path.exists():
            try:
                verify_private_file_permissions(path)
            except PermissionError as exc:
                raise ChatGPTPlanError(
                    "ChatGPT host identifier permissions are unsafe.",
                    code="unsafe_storage",
                ) from exc
            value = path.read_text(encoding="ascii").strip()
            try:
                parsed = value.removeprefix("urn:uuid:")
                uuid.UUID(parsed)
            except (ValueError, AttributeError) as exc:
                raise ChatGPTPlanError(
                    "ChatGPT host identifier is invalid.", code="invalid_host_id"
                ) from exc
            return value
        value = f"urn:uuid:{uuid.uuid4()}"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(value + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        set_private_file_permissions(path)
        return value

    def _registration_path(self) -> Path:
        return self.store.path.parent / "registration.json"

    def _load_registered_client_id(self) -> str | None:
        path = self._registration_path()
        if not path.exists():
            return None
        try:
            verify_private_directory_permissions(path.parent)
            verify_private_file_permissions(path)
        except PermissionError as exc:
            raise ChatGPTPlanError(
                "ChatGPT registration metadata permissions are unsafe.",
                code="unsafe_storage",
            ) from exc
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            client_id = value.get("client_id") if isinstance(value, dict) else None
        except (OSError, ValueError) as exc:
            raise ChatGPTPlanError(
                "ChatGPT registration metadata is unreadable.",
                code="registration_store_error",
            ) from exc
        if (
            not isinstance(client_id, str)
            or not client_id
            or client_id == "dynamic_agent_client"
        ):
            raise ChatGPTPlanError(
                "ChatGPT registration metadata is invalid.",
                code="registration_store_error",
            )
        return client_id

    def _save_registered_client_id(self, client_id: str) -> None:
        path = self._registration_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        set_private_directory_permissions(path.parent)
        fd, temporary_name = tempfile.mkstemp(
            prefix=".registration-", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            if os.name != "nt" and hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"client_id": client_id}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            set_private_file_permissions(path)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)
            raise

    def sign_out(self) -> dict[str, Any]:
        """Revoke the renewable session, then clear local secrets but retain registration."""
        with self._refresh_lock, self._exclusive_refresh_file_lock():
            return self._sign_out_locked()

    def _sign_out_locked(self) -> dict[str, Any]:
        profile = self.store.load()
        if not profile:
            return {"local_cleared": False, "remote_revoked": False}
        refresh_token = profile.get("refresh_token")
        remote_revoked = False
        if isinstance(refresh_token, str) and refresh_token:
            endpoint = None
            for attempt in range(2):
                try:
                    if endpoint is None:
                        discovery = self._http.get(
                            f"{ISSUER}/.well-known/openid-configuration"
                        )
                        discovery.raise_for_status()
                        discovery_data = discovery.json()
                        endpoint = (
                            discovery_data.get("revocation_endpoint")
                            if isinstance(discovery_data, dict)
                            else None
                        )
                        parsed = (
                            urlparse(endpoint) if isinstance(endpoint, str) else None
                        )
                        if (
                            not parsed
                            or parsed.scheme != "https"
                            or parsed.hostname != "auth.openai.com"
                            or parsed.port not in (None, 443)
                        ):
                            raise ValueError("untrusted revocation endpoint")
                    response = self._http.post(
                        endpoint,
                        data={
                            "token": refresh_token,
                            "token_type_hint": "refresh_token",
                            "client_id": profile["client_id"],
                        },
                    )
                    if response.status_code == 200:
                        remote_revoked = True
                        break
                    if response.status_code < 500:
                        break
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code < 500 or attempt == 1:
                        break
                except httpx.TransportError:
                    if attempt == 1:
                        break
                except (ValueError, KeyError):
                    break
                if attempt == 0:
                    time.sleep(0.5)
        self.store.clear()
        return {"local_cleared": True, "remote_revoked": remote_revoked}


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values and isinstance(values[0], str) else None


def _scopes(value: Any) -> set[str]:
    if isinstance(value, str):
        return {item for item in value.split() if item}
    if isinstance(value, (list, tuple, set)):
        return {item for item in value if isinstance(item, str) and item}
    return set()


def _required_token(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ChatGPTPlanError(
            "ChatGPT token response is missing a required credential.",
            code="invalid_token_response",
        )
    return value


def _expires_in(payload: dict[str, Any]) -> int:
    value = payload.get("expires_in", 3600)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ChatGPTPlanError(
            "ChatGPT token response has invalid expiry metadata.",
            code="invalid_token_response",
        )
    return int(value)


def _open_system_browser(url: str) -> bool:
    termux_opener = shutil.which("termux-open-url")
    if termux_opener:
        try:
            subprocess.Popen(
                [termux_opener, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError:
            return False
    return bool(webbrowser.open(url))


def main() -> int:
    parser = argparse.ArgumentParser(description="Jarvis Sign in with ChatGPT")
    parser.add_argument("command", choices=("login", "status", "logout", "prompt"))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--prompt", default="")
    parser.add_argument("--model", default=os.getenv("JARVIS_CHATGPT_MODEL", ""))
    args = parser.parse_args()
    oauth = ChatGPTPlanOAuth()
    try:
        if args.command == "login":
            result = oauth.sign_in(timeout_seconds=args.timeout)
            print(json.dumps(result, ensure_ascii=False))
        elif args.command == "status":
            profile = oauth.store.load()
            if not profile:
                print(json.dumps({"connected": False}))
            else:
                print(
                    json.dumps(
                        {
                            "connected": True,
                            "email": profile.get("email"),
                            "plan_usage_enabled": {
                                PLAN_USAGE_SCOPE,
                                "resource.invoke",
                            }.issubset(set(profile.get("scopes", []))),
                            "expires_at": profile.get("expires_at"),
                        },
                        ensure_ascii=False,
                    )
                )
        elif args.command == "logout":
            result = oauth.sign_out()
            print(json.dumps(result | {"connected": False}, ensure_ascii=False))
        else:
            if not args.prompt.strip():
                parser.error("prompt command requires --prompt")
            from app.adapters.infrastructure.chatgpt_plan_runtime import (
                ChatGPTPlanClient,
            )

            profile = oauth.load_valid_profile()
            with ChatGPTPlanClient(
                access_token=profile["access_token"], model=args.model or None
            ) as client:
                result = client.generate(({"role": "user", "content": args.prompt},))
            print(json.dumps(result, ensure_ascii=False))
        return 0
    except ChatGPTPlanError as exc:
        print(
            json.dumps(
                {"success": False, "code": exc.code, "error": str(exc)},
                ensure_ascii=False,
            )
        )
        return 1
    except (OSError, ValueError):
        print(
            json.dumps(
                {
                    "success": False,
                    "code": "local_configuration_error",
                    "error": "The local ChatGPT profile or credential storage is invalid.",
                },
                ensure_ascii=False,
            )
        )
        return 1
    finally:
        oauth.close()


if __name__ == "__main__":
    raise SystemExit(main())
