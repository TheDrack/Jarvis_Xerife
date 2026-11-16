from urllib.parse import parse_qs, urlparse

import pytest
from app.adapters.infrastructure.chatgpt_plan_auth import (
    ChatGPTPlanOAuth,
    build_authorization_url,
    create_pkce_pair,
)
from app.adapters.infrastructure.chatgpt_plan_runtime import (
    PLAN_USAGE_SCOPE,
    ChatGPTPlanCredentialStore,
    ChatGPTPlanError,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt


def test_pkce_pair_uses_s256_sha256_base64url_without_padding():
    import base64
    import hashlib

    verifier, challenge = create_pkce_pair()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert 43 <= len(verifier) <= 128
    assert challenge == expected


def test_new_registration_authorization_requests_plan_scopes_and_uses_dynamic_client():
    url = build_authorization_url(
        client_id="dynamic_agent_client",
        app_name="Jarvis Xerife",
        host_id="urn:uuid:00000000-0000-4000-8000-000000000000",
        redirect_uri="http://127.0.0.1:1455/auth/callback",
        state="state",
        nonce="nonce",
        code_challenge="challenge",
    )
    params = parse_qs(urlparse(url).query)
    assert url.startswith("https://auth.openai.com/api/accounts/authorize?")
    assert params["client_id"] == ["dynamic_agent_client"]
    assert params["agent_name_hint"] == ["Jarvis Xerife"]
    assert PLAN_USAGE_SCOPE in params["scope"][0].split()
    assert params["resource"] == ["https://api.openai.com/v1"]
    assert params["code_challenge_method"] == ["S256"]
    assert "client_secret" not in params


def test_returning_registration_reuses_issued_client_id_and_identity_hint():
    url = build_authorization_url(
        client_id="oaiapp_registered",
        app_name="Jarvis Xerife",
        host_id="urn:uuid:test",
        redirect_uri="http://127.0.0.1:1455/auth/callback",
        state="state",
        nonce="nonce",
        code_challenge="challenge",
        id_token_hint="old-id-token",
    )
    params = parse_qs(urlparse(url).query)
    assert params["client_id"] == ["oaiapp_registered"]
    assert params["id_token_hint"] == ["old-id-token"]
    assert "agent_name_hint" not in params


def test_identity_verification_checks_signature_audience_issuer_and_nonce():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public = private_key.public_key().public_numbers()

    def b64(value):
        import base64

        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    jwk = {
        "kty": "RSA",
        "kid": "test-key",
        "use": "sig",
        "alg": "RS256",
        "n": b64(public.n.to_bytes((public.n.bit_length() + 7) // 8, "big")),
        "e": b64(public.e.to_bytes((public.e.bit_length() + 7) // 8, "big")),
    }
    oauth = ChatGPTPlanOAuth(
        store=ChatGPTPlanCredentialStore("/tmp/jarvis-auth-test/profile.json"),
        browser_opener=lambda _url: True,
    )
    oauth._load_jwks = lambda: {"keys": [jwk]}
    token = jwt.encode(
        {
            "iss": "https://auth.openai.com",
            "aud": "oaiapp_test",
            "sub": "subject-1",
            "nonce": "nonce-1",
            "exp": 4102444800,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    assert (
        oauth._verify_identity(token, "oaiapp_test", nonce="nonce-1")["sub"]
        == "subject-1"
    )
    with pytest.raises(ChatGPTPlanError, match="validation failed"):
        oauth._verify_identity(token, "oaiapp_test", nonce="wrong")
    oauth.close()


def test_local_host_identifier_is_stable_and_owner_only(tmp_path):
    store = ChatGPTPlanCredentialStore(tmp_path / "private" / "profile.json")
    oauth = ChatGPTPlanOAuth(store=store, browser_opener=lambda _url: True)
    first = oauth._get_or_create_host_id()
    second = oauth._get_or_create_host_id()
    assert first == second
    assert first.startswith("urn:uuid:")
    assert (store.path.parent / "host-id").stat().st_mode & 0o077 == 0
    oauth.close()


def test_sign_in_completes_loopback_callback_and_persists_authorized_profile(tmp_path):
    import base64
    import threading
    from urllib.parse import urlencode

    import httpx

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public = private_key.public_key().public_numbers()

    def b64(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    jwk = {
        "kty": "RSA",
        "kid": "integration-key",
        "use": "sig",
        "alg": "RS256",
        "n": b64(public.n.to_bytes((public.n.bit_length() + 7) // 8, "big")),
        "e": b64(public.e.to_bytes((public.e.bit_length() + 7) // 8, "big")),
    }
    issued = {}

    def http_handler(request):
        if request.url.host == "auth.openai.com" and request.url.path.endswith(
            "/oauth/token"
        ):
            from urllib.parse import parse_qs

            values = parse_qs(request.content.decode())
            issued["client_id"] = values["client_id"][0]
            return httpx.Response(
                200,
                json={
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "id_token": issued["id_token"],
                    "scope": "openid profile email offline_access resource.invoke "
                    + PLAN_USAGE_SCOPE,
                    "expires_in": 3600,
                },
            )
        if request.url.path.endswith("/.well-known/jwks.json"):
            return httpx.Response(200, json={"keys": [jwk]})
        return httpx.Response(404)

    def open_browser(url):
        params = parse_qs(urlparse(url).query)
        issued["id_token"] = jwt.encode(
            {
                "iss": "https://auth.openai.com",
                "aud": "oaiapp_registered",
                "sub": "jarvis-user",
                "nonce": params["nonce"][0],
                "exp": 4102444800,
                "email": "jarvis@example.test",
            },
            private_pem,
            algorithm="RS256",
            headers={"kid": "integration-key"},
        )
        callback = (
            params["redirect_uri"][0]
            + "?"
            + urlencode(
                {
                    "code": "one-time-code",
                    "state": params["state"][0],
                    "client_id": "oaiapp_registered",
                }
            )
        )

        def send_callback():
            import time

            time.sleep(0.1)
            httpx.get(callback, timeout=5)

        threading.Thread(target=send_callback, daemon=True).start()
        return True

    http = httpx.Client(transport=httpx.MockTransport(http_handler))
    store = ChatGPTPlanCredentialStore(tmp_path / "private" / "profile.json")
    oauth = ChatGPTPlanOAuth(
        store=store,
        http_client=http,
        browser_opener=open_browser,
        initial_callback_port=0,
    )
    result = oauth.sign_in(timeout_seconds=30)

    profile = store.load()
    assert result["connected"] is True
    assert result["plan_usage_enabled"] is True
    assert profile["client_id"] == "oaiapp_registered"
    assert profile["subject"] == "jarvis-user"
    assert profile["access_token"] == "access-token"
    assert profile["refresh_token"] == "refresh-token"
    assert PLAN_USAGE_SCOPE in profile["scopes"]
    oauth.close()


def test_expired_profile_refreshes_with_rotating_token_and_preserves_grant(tmp_path):
    import httpx
    from app.adapters.infrastructure.chatgpt_plan_auth import RESOURCE

    store = ChatGPTPlanCredentialStore(tmp_path / "private" / "profile.json")
    store.save(
        {
            "client_id": "oaiapp_existing",
            "subject": "subject-1",
            "access_token": "expired-access",
            "refresh_token": "old-refresh",
            "id_token": "retained-id-token",
            "scopes": ["resource.invoke", PLAN_USAGE_SCOPE],
            "expires_at": 1,
        }
    )
    captured = {}

    def handler(request):
        captured["form"] = dict(
            __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(
                request.content.decode()
            )
        )
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "rotated-refresh",
                "expires_in": 3600,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    oauth = ChatGPTPlanOAuth(
        store=store, http_client=client, browser_opener=lambda _url: True
    )
    profile = oauth.load_valid_profile()

    assert profile["access_token"] == "new-access"
    assert profile["refresh_token"] == "rotated-refresh"
    assert captured["form"]["grant_type"] == ["refresh_token"]
    assert captured["form"]["client_id"] == ["oaiapp_existing"]
    assert captured["form"]["resource"] == [RESOURCE]
    assert "scope" not in captured["form"]
    oauth.close()


def test_sign_out_revokes_refresh_token_and_clears_only_local_secrets(tmp_path):
    import httpx

    store = ChatGPTPlanCredentialStore(tmp_path / "private" / "profile.json")
    store.save(
        {
            "client_id": "oaiapp_existing",
            "subject": "subject-1",
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "scopes": ["resource.invoke", PLAN_USAGE_SCOPE],
        }
    )
    calls = []

    def handler(request):
        calls.append((request.url.path, request.content.decode()))
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "revocation_endpoint": "https://auth.openai.com/api/accounts/oauth/revoke"
                },
            )
        if request.url.path.endswith("/oauth/revoke"):
            return httpx.Response(200)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    oauth = ChatGPTPlanOAuth(
        store=store, http_client=client, browser_opener=lambda _url: True
    )
    result = oauth.sign_out()

    assert result == {"local_cleared": True, "remote_revoked": True}
    assert store.load() is None
    assert calls[1][1].find("refresh-secret") >= 0
    oauth.close()


def test_issued_registration_is_retained_when_code_exchange_fails(tmp_path):
    import httpx

    store = ChatGPTPlanCredentialStore(tmp_path / "private" / "profile.json")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(503, json={"error": "temporary"})
        )
    )
    oauth = ChatGPTPlanOAuth(
        store=store, http_client=client, browser_opener=lambda _url: True
    )

    with pytest.raises(ChatGPTPlanError, match="token exchange failed"):
        oauth._complete_callback(
            {
                "state": ["state"],
                "code": ["one-time"],
                "client_id": ["oaiapp_registered"],
            },
            state="state",
            nonce="nonce",
            verifier="verifier",
            redirect_uri="http://127.0.0.1:1455/auth/callback",
            expected_client_id="dynamic_agent_client",
            previous=None,
            host_id="urn:uuid:00000000-0000-4000-8000-000000000000",
        )

    assert oauth._load_registered_client_id() == "oaiapp_registered"
    oauth.close()


def test_concurrent_expiry_checks_only_refresh_rotating_token_once(tmp_path):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    import httpx

    store = ChatGPTPlanCredentialStore(tmp_path / "private" / "profile.json")
    store.save(
        {
            "client_id": "oaiapp_existing",
            "subject": "subject-1",
            "access_token": "expired-access",
            "refresh_token": "old-refresh",
            "scopes": ["resource.invoke", PLAN_USAGE_SCOPE],
            "expires_at": 1,
        }
    )
    calls = []
    call_lock = threading.Lock()

    def handler(_request):
        with call_lock:
            calls.append(1)
        time.sleep(0.15)
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    oauth = ChatGPTPlanOAuth(
        store=store, http_client=client, browser_opener=lambda _url: True
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens = list(pool.map(lambda _index: oauth.get_access_token(), range(2)))

    assert tokens == ["new-access", "new-access"]
    assert len(calls) == 1
    oauth.close()


def test_token_exchange_exposes_only_machine_readable_oauth_error_code(tmp_path):
    import httpx

    store = ChatGPTPlanCredentialStore(tmp_path / "private" / "profile.json")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                400,
                json={
                    "error": "invalid_grant",
                    "error_description": "sensitive provider detail",
                },
            )
        )
    )
    oauth = ChatGPTPlanOAuth(
        store=store, http_client=client, browser_opener=lambda _url: True
    )

    with pytest.raises(ChatGPTPlanError) as captured:
        oauth._token_request({"grant_type": "authorization_code"})

    assert captured.value.code == "oauth_invalid_grant"
    assert "invalid_grant" in str(captured.value)
    assert "sensitive provider detail" not in str(captured.value)
    oauth.close()


def test_sign_out_retries_discovery_failure_before_revoking(tmp_path):
    import httpx

    store = ChatGPTPlanCredentialStore(tmp_path / "private" / "profile.json")
    store.save(
        {
            "client_id": "oaiapp_existing",
            "subject": "subject-1",
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "scopes": ["resource.invoke", PLAN_USAGE_SCOPE],
        }
    )
    discovery_attempts = []

    def handler(request):
        if request.url.path.endswith("openid-configuration"):
            discovery_attempts.append(1)
            if len(discovery_attempts) == 1:
                return httpx.Response(503)
            return httpx.Response(
                200,
                json={
                    "revocation_endpoint": "https://auth.openai.com/api/accounts/oauth/revoke"
                },
            )
        if request.url.path.endswith("/oauth/revoke"):
            return httpx.Response(200)
        return httpx.Response(404)

    oauth = ChatGPTPlanOAuth(
        store=store,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        browser_opener=lambda _url: True,
    )
    result = oauth.sign_out()

    assert result["remote_revoked"] is True
    assert len(discovery_attempts) == 2
    assert store.load() is None
    oauth.close()
