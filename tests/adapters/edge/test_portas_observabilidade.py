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
    observer._events = __import__("collections").deque(maxlen=100)
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

def test_cdp_endpoint_accepts_local_websocket_and_rejects_remote_hosts():
    from app.adapters.edge.portas_core import configurar_cdp_url

    accepted = configurar_cdp_url("ws://127.0.0.1:56415/devtools/browser/test-id")
    rejected = configurar_cdp_url("ws://192.168.1.10:9222/devtools/browser/test-id")
    assert accepted["success"] is True
    assert rejected["success"] is False
    assert "loopback" in rejected["error"]
