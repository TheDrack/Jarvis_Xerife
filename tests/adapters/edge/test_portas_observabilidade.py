import base64
from collections import deque

from app.adapters.edge.portas_observabilidade import (
    BrowserTrafficObserver,
    sanitizar_payload,
    sanitizar_url,
)


def test_url_removes_credentials_and_query_values():
    safe, host = sanitizar_url("https://user:pass@example.com/api/camera?token=abc&id=7")
    assert host == "example.com"
    assert safe == "https://example.com/api/camera?token=%5BREDACTED%5D&id=%5BREDACTED%5D"
    assert "user" not in safe
    assert "pass" not in safe
    assert "abc" not in safe


def test_payload_is_metadata_only_by_default():
    payload = sanitizar_payload('{"command":"open","token":"secret-value"}', enabled=False)
    assert payload == {"kind": "text", "characters": len('{"command":"open","token":"secret-value"}')}
    assert "secret-value" not in str(payload)


def test_payload_preview_redacts_sensitive_json_fields():
    payload = sanitizar_payload(
        '{"command":"open","token":"secret-value","camera":"front"}',
        enabled=True,
    )
    assert "secret-value" not in payload["preview"]
    assert "[REDACTED]" in payload["preview"]
    assert '"camera":"front"' in payload["preview"]


def test_websocket_frame_events_are_recorded_without_payload_by_default():
    class FakeWebSocket:
        url = "wss://echo.websocket.org/socket?access_token=hidden"

        def __init__(self):
            self.handlers = {}

        def on(self, event, callback):
            self.handlers[event] = callback

    observer = BrowserTrafficObserver()
    websocket = FakeWebSocket()
    observer._on_websocket(websocket)
    websocket.handlers["framesent"]("hello")
    websocket.handlers["framereceived"]("hello")

    events = observer.events()["events"]
    assert [event["type"] for event in events] == [
        "websocket_open",
        "websocket_frame",
        "websocket_frame",
    ]
    assert events[1]["direction"] == "sent"
    assert events[2]["direction"] == "received"
    assert events[1]["payload"] == {"kind": "text", "characters": 5}
    assert "hidden" not in str(events)


def test_websocket_payload_opt_in_still_redacts_secrets():
    class FakeWebSocket:
        url = "wss://echo.websocket.org/socket"

        def __init__(self):
            self.handlers = {}

        def on(self, event, callback):
            self.handlers[event] = callback

    observer = BrowserTrafficObserver()
    observer._capture_payloads = True
    websocket = FakeWebSocket()
    observer._on_websocket(websocket)
    websocket.handlers["framesent"]('{"action":"ptz","password":"dont-log-me"}')

    events = observer.events()["events"]
    frame = events[-1]
    assert frame["payload"]["preview"].find("dont-log-me") == -1
    assert "[REDACTED]" in frame["payload"]["preview"]


def test_event_buffer_is_bounded_and_supports_incremental_filtering():
    observer = BrowserTrafficObserver(max_events=100)
    observer._events = deque(maxlen=100)
    observer._emit("http_request", host="camera.example", method="GET")
    observer._emit("http_response", host="other.example", status=200)

    result = observer.events(limit=10, after_id=1, host_contains="other")
    assert result["count"] == 1
    assert result["events"][0]["type"] == "http_response"
    assert result["next_after_id"] == 2


def test_http_request_capture_is_opt_in_and_redacts_sensitive_fields():
    class FakeRequest:
        url = "https://api.example.test/camera?token=query-secret"
        method = "POST"
        resource_type = "xhr"
        post_data = '{"operation":"ptz","password":"body-secret","direction":"left"}'
        headers = {
            "content-type": "application/json",
            "authorization": "Bearer header-secret",
            "cookie": "session=secret",
            "x-requested-with": "XMLHttpRequest",
        }

    observer = BrowserTrafficObserver()
    observer._capture_payloads = True
    request = FakeRequest()
    observer._on_request(request)
    event = observer.events()["events"][0]
    assert event["method"] == "POST"
    assert event["resource_type"] == "xhr"
    assert "query-secret" not in event["url"]
    assert "body-secret" not in event["request_payload"]["preview"]
    assert "header-secret" not in str(event)
    assert "cookie" not in event.get("safe_headers", {})
    assert event["safe_headers"]["content-type"] == "application/json"


def test_http_response_correlates_with_request():
    class FakeRequest:
        url = "https://api.example.test/camera"
        method = "GET"
        resource_type = "fetch"
        post_data = None
        headers = {}

    class FakeResponse:
        url = "https://api.example.test/camera"
        status = 200
        status_text = "OK"
        headers = {"content-type": "application/json"}

        def __init__(self, request):
            self.request = request

    observer = BrowserTrafficObserver()
    request = FakeRequest()
    observer._on_request(request)
    request_event = observer.events()["events"][0]
    observer._on_response(FakeResponse(request))
    response_event = observer.events()["events"][1]
    assert response_event["request_id"] == request_event["request_id"]
    assert response_event["content_type"] == "application/json"


def test_binary_websocket_payload_never_exposes_raw_bytes():
    payload = sanitizar_payload(b"\x00private-binary-token", enabled=True)
    assert payload == {"kind": "binary", "bytes": len(b"\x00private-binary-token")}
    assert "preview_hex" not in payload


def test_request_response_correlation_survives_distinct_playwright_wrappers():
    implementation = object()

    class FakeRequest:
        _impl_obj = implementation
        url = "https://api.example.test/action"
        method = "POST"
        resource_type = "fetch"
        post_data = None
        headers = {}

    class FakeResponse:
        url = "https://api.example.test/action"
        status = 204
        status_text = "No Content"
        headers = {"content-type": "application/json"}

        def __init__(self):
            self.request = FakeRequest()

    observer = BrowserTrafficObserver()
    observer._on_request(FakeRequest())
    request_event = observer.events()["events"][0]
    observer._on_response(FakeResponse())
    response_event = observer.events()["events"][1]
    assert response_event["request_id"] == request_event["request_id"]


def test_cdp_endpoint_accepts_local_websocket_and_rejects_remote_hosts(monkeypatch):
    from app.adapters.edge import portas_core

    original = portas_core.CDP_URL
    accepted = portas_core.configurar_cdp_url("ws://127.0.0.1:56415/devtools/browser/test-id")
    rejected = portas_core.configurar_cdp_url("ws://192.168.1.10:9222/devtools/browser/test-id")
    assert accepted["success"] is True
    assert rejected["success"] is False
    assert "loopback" in rejected["error"]
    monkeypatch.setattr(portas_core, "CDP_URL", original)


def test_media_response_capture_rejects_unbounded_and_manifest_bodies(monkeypatch):
    import asyncio
    import app.adapters.edge.portas_observabilidade as module

    class Response:
        url = "https://video.example/file?token=private"
        headers = {"content-length": str(module._MEDIA_RESPONSE_BODY_LIMIT + 1)}
        async def body(self):
            raise AssertionError("oversized response must be rejected before body materialization")

    observer = BrowserTrafficObserver()
    asyncio.run(observer._capture_response_body(Response(), 1, "video/mp4"))

    class ManifestResponse(Response):
        headers = {"content-length": "128"}
        async def body(self):
            raise AssertionError("manifest bodies must never be materialized")

    asyncio.run(
        observer._capture_response_body(
            ManifestResponse(), 2, "application/vnd.apple.mpegurl"
        )
    )


def test_media_response_capture_redacts_url_before_opening_stream(monkeypatch):
    import asyncio
    import app.adapters.edge.portas_observabilidade as module

    seen = {}

    class Engine:
        def open_stream(self, url, **kwargs):
            seen["url"] = url
            seen["kwargs"] = kwargs
            return "stream-1"
        def append(self, stream_id, body, **kwargs):
            seen["body"] = body
            return True
        def close_stream(self, stream_id):
            seen["closed"] = stream_id

    class Response:
        url = "https://video.example/file?token=private"
        headers = {"content-length": "4", "content-encoding": "identity"}
        async def body(self):
            return b"data"

    monkeypatch.setattr(module, "media_engine", Engine())
    observer = BrowserTrafficObserver()
    asyncio.run(observer._capture_response_body(Response(), 3, "video/mp4"))

    assert "private" not in seen["url"]
    assert "%5BREDACTED%5D" in seen["url"]
    assert seen["body"] == b"data"
    assert seen["closed"] == "stream-1"


def test_request_finished_reports_duration_and_same_request_id():
    class FakeRequest:
        url = "https://api.example.test/camera"
        method = "POST"
        resource_type = "xhr"
        post_data = None
        headers = {}

    observer = BrowserTrafficObserver()
    request = FakeRequest()
    observer._on_request(request)
    request_event = observer.events()["events"][0]
    observer._on_request_finished(request)
    finished_event = observer.events()["events"][1]
    assert finished_event["type"] == "http_request_finished"
    assert finished_event["request_id"] == request_event["request_id"]
    assert finished_event["duration_ms"] is not None


def test_media_capture_preserves_binary_bytes_in_base64_chunks():
    observer = BrowserTrafficObserver()
    observer._media_streams["stream-1"] = {
        "stream_id": "stream-1",
        "mime_type": "audio/mp4",
        "status": "streaming",
    }
    payload = b"\x00\xffftypisom\x00binary-media\x80"
    observer._store_media_bytes("stream-1", payload)

    result = observer.media_chunks("stream-1", after_sequence=0, limit=10)
    assert result["success"] is True
    assert result["count"] == 1
    assert base64.b64decode(result["chunks"][0]["data"]) == payload
    assert result["chunks"][0]["sequence"] == 1
    assert result["chunks"][0]["offset"] == 0


def test_media_capture_enforces_per_stream_byte_limit():
    from app.adapters.edge.portas_observabilidade import _MEDIA_STREAM_MAX_BYTES

    observer = BrowserTrafficObserver()
    observer._media_streams["stream-limit"] = {
        "stream_id": "stream-limit",
        "mime_type": "video/mp4",
        "status": "streaming",
    }

    captured = observer._store_media_bytes(
        "stream-limit", b"x" * (_MEDIA_STREAM_MAX_BYTES + 1024)
    )

    assert captured == _MEDIA_STREAM_MAX_BYTES
    result = observer.media_chunks("stream-limit", limit=32)
    assert result["success"] is True
    assert sum(chunk["bytes"] for chunk in result["chunks"]) == _MEDIA_STREAM_MAX_BYTES
    assert result["status"] == "truncated"


def test_media_capture_buffer_is_bounded_and_reports_evicted_sequence_gap():
    observer = BrowserTrafficObserver()
    observer._media_streams["stream-1"] = {
        "stream_id": "stream-1",
        "mime_type": "video/mp4",
        "status": "streaming",
    }
    observer._media_chunks = deque(maxlen=2)
    observer._store_media_bytes("stream-1", b"chunk-1")
    observer._store_media_bytes("stream-1", b"chunk-2")
    observer._store_media_bytes("stream-1", b"chunk-3")

    result = observer.media_chunks("stream-1", after_sequence=0, limit=10)
    assert [chunk["sequence"] for chunk in result["chunks"]] == [2, 3]
    assert result["first_available_sequence"] == 2
    assert result["gap"] is True
    assert base64.b64decode(result["chunks"][0]["data"]) == b"chunk-2"


def test_media_capture_classifies_ump_and_declared_media_mime():
    observer = BrowserTrafficObserver()
    assert observer._is_media_response({
        "url": "https://video.example/videoplayback",
        "mimeType": "application/vnd.yt-ump",
    })
    assert not observer._is_media_response({
        "url": "https://video.example/videoplayback?mime=audio%2Fmp4&token=secret",
        "mimeType": "application/octet-stream",
        "resourceType": "XHR",
    })
    assert not observer._is_media_response({
        "url": "https://video.example/videoplayback?mime=audio%2Fmp4&token=secret",
        "mimeType": "application/octet-stream",
        "resourceType": "Media",
    })
    assert observer._is_media_response({
        "url": "https://video.example/videoplayback",
        "mimeType": "video/mp4",
        "resourceType": "Media",
    })
    assert not observer._is_media_response({
        "url": "https://video.example/master.m3u8",
        "mimeType": "application/vnd.apple.mpegurl",
        "resourceType": "Manifest",
    })
    assert not observer._is_media_response({
        "url": "https://api.example/data",
        "mimeType": "application/json",
    })
    assert not observer._is_media_response({
        "url": "https://api.example/data?mime=audio%2Fmp4",
        "mimeType": "application/json",
        "headers": {"content-type": "application/json"},
    })


def test_media_data_received_event_preserves_binary_response_bytes():
    observer = BrowserTrafficObserver()
    session = object()
    payload = b"\x00\xff\x00ftypisom\x01\x02"
    observer._media_streams["stream-2"] = {
        "stream_id": "stream-2",
        "mime_type": "application/vnd.yt-ump",
        "protocol": "ump",
        "status": "streaming",
    }
    observer._media_request_streams[(id(session), "request-7")] = "stream-2"

    observer._on_media_data_received(session, {
        "requestId": "request-7",
        "timestamp": 123.5,
        "data": base64.b64encode(payload).decode("ascii"),
    })

    result = observer.media_chunks("stream-2", after_sequence=0, limit=10)
    assert result["protocol"] == "ump"
    assert base64.b64decode(result["chunks"][0]["data"]) == payload


def test_clear_removes_media_stream_metadata_and_indexes_without_stopping_capture():
    observer = BrowserTrafficObserver()
    observer._active = True
    observer._capture_media = True
    observer._emit("http_request", host="media.example", method="GET")
    observer._media_streams["stream-clear"] = {
        "stream_id": "stream-clear",
        "url": "https://media.example/video?token=%5BREDACTED%5D",
        "host": "media.example",
        "mime_type": "video/mp4",
        "status": "streaming",
    }
    observer._media_request_streams[(123, "request-clear")] = "stream-clear"
    observer._media_sequences["stream-clear"] = 1
    observer._media_offsets["stream-clear"] = 6
    observer._media_chunks.append({
        "stream_id": "stream-clear",
        "sequence": 1,
        "offset": 0,
        "bytes": 6,
        "data": base64.b64encode(b"secret").decode("ascii"),
    })

    result = observer.clear()

    assert result["success"] is True
    assert result["cleared"] == 1
    assert result["media_chunks_cleared"] is True
    assert result["media_streams_cleared"] == 1
    assert result["media_indexes_cleared"] is True
    assert observer.events()["count"] == 0
    media_events = observer.media_events()
    assert media_events["streams"] == []
    assert media_events["buffered_chunks"] == 0
    assert observer.media_chunks("stream-clear")["error"] == "stream_not_found"
    assert observer._media_request_streams == {}
    assert observer._media_sequences == {}
    assert observer._media_offsets == {}
    assert observer.status()["active"] is True
    assert observer.status()["media_capture"] is True
