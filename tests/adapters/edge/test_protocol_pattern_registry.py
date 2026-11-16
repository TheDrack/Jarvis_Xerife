import json

import pytest
from app.adapters.edge.protocol_pattern_registry import ProtocolPatternRegistry


def test_observation_is_persisted_as_redacted_versioned_pattern(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    observation = {
        "transport": "https",
        "method": "POST",
        "url": "https://api.example.test/v1/messages?token=query-secret",
        "request_headers": {
            "content-type": "application/json",
            "authorization": "Bearer header-secret",
        },
        "request_body": {
            "conversation_id": "conv-123",
            "message": "hello world",
            "access_token": "body-secret",
        },
        "response": {
            "status": 200,
            "body": {"message_id": "msg-123", "session_cookie": "cookie-secret"},
        },
    }

    result = registry.record_observation(
        package="com.example.chat",
        app_version="2.4.1",
        operation="send_message",
        observation=observation,
    )

    assert result["status"] == "observed"
    assert result["package"] == "com.example.chat"
    assert result["app_version"] == "2.4.1"
    assert result["operation"] == "send_message"
    assert result["pattern"]["request"]["method"] == "POST"
    assert result["pattern"]["request"]["path"] == "/v1/messages"
    assert result["pattern"]["request"]["body_schema"] == {
        "conversation_id": "string",
        "message": "string",
        "access_token": "redacted",
    }
    assert result["pattern"]["response"]["body_schema"] == {
        "message_id": "string",
        "session_cookie": "redacted",
    }

    stored = (tmp_path / "protocol-patterns.jsonl").read_text(encoding="utf-8")
    for secret in ("query-secret", "header-secret", "body-secret", "cookie-secret", "conv-123", "hello world"):
        assert secret not in stored
    assert json.loads(stored.splitlines()[0]) == result


def test_observation_rejects_invalid_identity_and_unstructured_input(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    with pytest.raises(ValueError, match="package"):
        registry.record_observation(
            package="",
            app_version="1",
            operation="send",
            observation={"method": "POST"},
        )
    with pytest.raises(ValueError, match="observation"):
        registry.record_observation(
            package="com.example.app",
            app_version="1",
            operation="send",
            observation=[],
        )


def test_pattern_lifecycle_requires_validation_evidence_before_reuse(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    record = registry.record_observation(
        package="com.example.app",
        app_version="1.0",
        operation="send",
        observation={"method": "POST", "url": "https://api.example.test/send"},
    )

    with pytest.raises(ValueError, match="validation"):
        registry.transition(record["id"], "reusable")

    validated = registry.transition(
        record["id"], "validated", evidence="reproduced against owned test server"
    )
    reusable = registry.transition(
        record["id"], "reusable", evidence="approved controlled replay"
    )
    assert validated["status"] == "validated"
    assert reusable["status"] == "reusable"


def test_registry_lists_patterns_and_compares_app_versions(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    first = registry.record_observation(
        package="com.example.app",
        app_version="1.0",
        operation="send",
        observation={"method": "POST", "url": "https://api.example.test/v1/send"},
    )
    second = registry.record_observation(
        package="com.example.app",
        app_version="2.0",
        operation="send",
        observation={"method": "POST", "url": "https://api.example.test/v2/send"},
    )

    assert [item["id"] for item in registry.list_patterns(package="com.example.app")] == [
        first["id"], second["id"]
    ]
    diff = registry.compare_versions(
        package="com.example.app", operation="send", older="1.0", newer="2.0"
    )
    assert diff["changed"] is True
    assert diff["changes"] == ["request.path"]


def test_observation_masks_dynamic_path_segments(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    result = registry.record_observation(
        package="com.example.app",
        app_version="1.0",
        operation="get_profile",
        observation={"method": "GET", "url": "https://api.example.test/v1/users/123456789/profile"},
    )
    assert result["pattern"]["request"]["path"] == "/v1/users/[ID]/profile"


def test_mcp_exposes_pattern_record_list_transition_and_version_diff(tmp_path, monkeypatch):
    import app.adapters.edge.portas_observabilidade as module
    import app.adapters.edge.protocol_pattern_mcp_tools as protocol_tools

    class FakeMcp:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def register(function):
                self.tools[function.__name__] = function
                return function
            return register

    def tracked_action(_label):
        return lambda function: function

    monkeypatch.setattr(
        protocol_tools, "protocol_registry", ProtocolPatternRegistry(tmp_path)
    )
    server = FakeMcp()
    module.registrar_observabilidade_portas(server, tracked_action)

    record = server.tools["protocol_pattern_record_observation"](
        "com.example.app", "1.0", "send", {"method": "POST", "url": "https://api.example.test/send"}
    )
    listed = server.tools["protocol_pattern_list"]("com.example.app", "send")
    validated = server.tools["protocol_pattern_transition"](
        record["id"], "validated", "validated on controlled test server"
    )
    assert listed["count"] == 1
    assert validated["status"] == "validated"
    assert {
        "protocol_pattern_record_observation",
        "protocol_pattern_list",
        "protocol_pattern_transition",
        "protocol_pattern_compare_versions",
    }.issubset(server.tools)


def test_imports_only_uniquely_attributed_android_flow_metadata(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    flows = [
        {
            "protocol": "tcp",
            "remote_ip": "203.0.113.10",
            "remote_port": 443,
            "package_names": ["com.example.chat"],
            "attribution_status": "resolved",
            "first_seen_at": "2026-11-16T12:00:00Z",
            "last_seen_at": "2026-11-16T12:00:05Z",
            "protocol_observations": [
                {"kind": "tls_sni", "value": "api.example.test", "source": "tls_client_hello"}
            ],
        },
        {
            "protocol": "udp",
            "remote_ip": "203.0.113.11",
            "remote_port": 53,
            "package_names": ["com.example.chat", "com.example.other"],
            "attribution_status": "shared_uid",
            "protocol_observations": [
                {"kind": "dns_query", "value": "shared.example.test", "source": "dns"}
            ],
        },
    ]

    result = registry.record_flow_observations(
        package="com.example.chat", app_version="unknown", flows=flows
    )

    assert result["recorded"] == 1
    assert result["skipped_unattributed"] == 1
    records = registry.list_patterns(package="com.example.chat")
    assert len(records) == 1
    record = records[0]
    assert record["operation"] == "tls_sni"
    assert record["source"] == "android_vpn_passive_metadata"
    assert record["confidence"] == "observed"
    assert record["network_pattern"] == {
        "kind": "tls_sni",
        "hostname": "api.example.test",
        "source": "tls_client_hello",
        "transport": "tcp",
        "remote_ip": "203.0.113.10",
        "remote_port": 443,
        "first_seen_at": "2026-11-16T12:00:00Z",
        "attribution": "uniquely_resolved",
    }


def test_flow_import_rejects_invalid_or_unsafe_protocol_metadata(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    invalid_flow = {
        "protocol": "tcp",
        "remote_ip": "203.0.113.10",
        "remote_port": 443,
        "package_names": ["com.example.chat"],
        "attribution_status": "resolved",
        "protocol_observations": [
            {"kind": "http_host", "value": "https://example.test/private", "source": "http"}
        ],
    }
    with pytest.raises(ValueError, match="hostname"):
        registry.record_flow_observations(
            package="com.example.chat", app_version="1.0", flows=[invalid_flow]
        )


def test_mcp_exposes_android_flow_pattern_import(tmp_path, monkeypatch):
    import app.adapters.edge.protocol_pattern_mcp_tools as module

    class FakeMcp:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def register(function):
                self.tools[function.__name__] = function
                return function
            return register

    monkeypatch.setattr(module, "protocol_registry", ProtocolPatternRegistry(tmp_path))
    server = FakeMcp()
    module.register_protocol_pattern_tools(
        server, lambda _label: lambda function: function
    )

    assert {
        "protocol_pattern_record_observation",
        "protocol_pattern_import_android_flows",
        "protocol_pattern_list",
        "protocol_pattern_transition",
        "protocol_pattern_compare_versions",
    }.issubset(server.tools)


def test_version_comparison_ignores_network_metadata_records(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    registry.record_flow_observations(
        package="com.example.chat",
        app_version="unknown",
        flows=[{
            "protocol": "tcp",
            "remote_ip": "203.0.113.10",
            "remote_port": 443,
            "package_names": ["com.example.chat"],
            "attribution_status": "resolved",
            "protocol_observations": [
                {"kind": "tls_sni", "value": "api.example.test", "source": "tls_client_hello"}
            ],
        }],
    )
    registry.record_observation(
        package="com.example.chat", app_version="1.0", operation="send",
        observation={"method": "POST", "url": "https://api.example.test/v1/send"},
    )
    registry.record_observation(
        package="com.example.chat", app_version="2.0", operation="send",
        observation={"method": "POST", "url": "https://api.example.test/v2/send"},
    )

    diff = registry.compare_versions(
        package="com.example.chat", operation="send", older="1.0", newer="2.0"
    )

    assert diff["changed"] is True
    assert diff["changes"] == ["request.path"]


def test_version_comparison_supports_android_network_patterns(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    for version, hostname in (("1.0", "api.example.test"), ("2.0", "edge.example.test")):
        registry.record_flow_observations(
            package="com.example.chat",
            app_version=version,
            flows=[{
                "protocol": "tcp",
                "remote_ip": "203.0.113.10",
                "remote_port": 443,
                "package_names": ["com.example.chat"],
                "attribution_status": "resolved",
                "protocol_observations": [
                    {"kind": "tls_sni", "value": hostname, "source": "tls_client_hello"}
                ],
            }],
        )

    diff = registry.compare_versions(
        package="com.example.chat", operation="tls_sni", older="1.0", newer="2.0"
    )

    assert diff["changed"] is True
    assert diff["changes"] == ["network_pattern.hostname"]


def test_repeated_android_flow_observation_does_not_duplicate_pattern(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    flow = {
        "protocol": "tcp",
        "remote_ip": "203.0.113.10",
        "remote_port": 443,
        "package_names": ["com.example.chat"],
        "attribution_status": "resolved",
        "protocol_observations": [
            {"kind": "tls_sni", "value": "api.example.test", "source": "tls_client_hello"}
        ],
    }

    first = registry.record_flow_observations(
        package="com.example.chat", app_version="1.0", flows=[flow]
    )
    repeated_flow = {
        **flow,
        "first_seen_at": "2026-11-16T12:30:00Z",
        "last_seen_at": "2026-11-16T12:30:05Z",
    }
    second = registry.record_flow_observations(
        package="com.example.chat", app_version="1.0", flows=[repeated_flow]
    )

    assert first["recorded"] == 1
    assert second["recorded"] == 0
    assert second["already_known"] == 1
    assert len(registry.list_patterns(package="com.example.chat")) == 1


def test_network_version_comparison_compares_all_observed_hosts(tmp_path):
    registry = ProtocolPatternRegistry(tmp_path)
    version_flows = {
        "1.0": ("api.example.test", "cdn.example.test"),
        "2.0": ("api.example.test", "edge.example.test"),
    }
    for version, hosts in version_flows.items():
        flows = [{
            "protocol": "tcp",
            "remote_ip": f"203.0.113.{index + 10}",
            "remote_port": 443,
            "package_names": ["com.example.chat"],
            "attribution_status": "resolved",
            "protocol_observations": [
                {"kind": "tls_sni", "value": host, "source": "tls_client_hello"}
            ],
        } for index, host in enumerate(hosts)]
        registry.record_flow_observations(
            package="com.example.chat", app_version=version, flows=flows
        )

    diff = registry.compare_versions(
        package="com.example.chat", operation="tls_sni", older="1.0", newer="2.0"
    )

    assert diff["changed"] is True
    assert diff["changes"] == ["network_pattern.hostname"]


def test_live_android_import_uses_paired_snapshot_and_package_manager_version(tmp_path, monkeypatch):
    import app.adapters.edge.android_network_mcp_tools as android_network_tools
    import app.adapters.edge.protocol_pattern_mcp_tools as module

    class FakeMcp:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def register(function):
                self.tools[function.__name__] = function
                return function
            return register

    flow = {
        "protocol": "tcp",
        "remote_ip": "203.0.113.20",
        "remote_port": 443,
        "package_names": ["com.example.chat"],
        "attribution_status": "resolved",
        "package_versions": [{
            "package_name": "com.example.chat",
            "version_name": "4.2.1",
            "version_code": 42001,
        }],
        "protocol_observations": [
            {"kind": "tls_sni", "value": "api.example.test", "source": "tls_client_hello"}
        ],
    }
    monkeypatch.setattr(
        android_network_tools,
        "read_android_network_flows_snapshot",
        lambda package: {
            "capture_owner": "jarvis",
            "capture_reason": "capturing",
            "flow_metadata_opt_in": True,
            "payload_metadata_opt_in": True,
            "flow_count": 1,
            "flows": [flow],
        },
    )
    monkeypatch.setattr(module, "protocol_registry", ProtocolPatternRegistry(tmp_path))
    server = FakeMcp()
    module.register_protocol_pattern_tools(server, include_live_android=True)

    result = server.tools["protocol_pattern_import_live_android_flows"]("com.example.chat")

    assert result["success"] is True
    assert result["app_version"] == "4.2.1+42001"
    assert result["recorded"] == 1
    assert result["protocol_observations_seen"] == 1
    assert "protocol_pattern_import_live_android_flows" in server.tools


def test_desktop_pattern_registry_does_not_register_local_android_capture_tool():
    import app.adapters.edge.protocol_pattern_mcp_tools as module

    class FakeMcp:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def register(function):
                self.tools[function.__name__] = function
                return function
            return register

    server = FakeMcp()
    module.register_protocol_pattern_tools(server)

    assert "protocol_pattern_import_live_android_flows" not in server.tools
    assert "protocol_pattern_analyze_package" in server.tools


def test_live_android_import_refuses_external_vpn_snapshots(monkeypatch, tmp_path):
    import app.adapters.edge.android_network_mcp_tools as android_network_tools
    import app.adapters.edge.protocol_pattern_mcp_tools as module

    class FakeMcp:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def register(function):
                self.tools[function.__name__] = function
                return function
            return register

    monkeypatch.setattr(
        android_network_tools,
        "read_android_network_flows_snapshot",
        lambda _package: {
            "capture_owner": "external",
            "capture_reason": "external_vpn_not_owned",
            "flow_metadata_opt_in": True,
            "payload_metadata_opt_in": True,
            "flow_count": 0,
            "flows": [],
        },
    )
    registry = ProtocolPatternRegistry(tmp_path)
    monkeypatch.setattr(module, "protocol_registry", registry)
    server = FakeMcp()
    module.register_protocol_pattern_tools(server, include_live_android=True)

    result = server.tools["protocol_pattern_import_live_android_flows"]("com.example.chat")

    assert result["success"] is False
    assert result["status"] == "capture_unavailable"
    assert registry.list_patterns() == []


def test_package_analysis_groups_hosts_versions_and_lifecycle_status(tmp_path, monkeypatch):
    import app.adapters.edge.protocol_pattern_mcp_tools as module

    class FakeMcp:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def register(function):
                self.tools[function.__name__] = function
                return function
            return register

    registry = ProtocolPatternRegistry(tmp_path)
    registry.record_flow_observations(
        package="com.example.chat",
        app_version="4.2.1+42001",
        flows=[{
            "protocol": "tcp",
            "remote_ip": "203.0.113.20",
            "remote_port": 443,
            "package_names": ["com.example.chat"],
            "attribution_status": "resolved",
            "protocol_observations": [
                {"kind": "tls_sni", "value": "api.example.test", "source": "tls_client_hello"}
            ],
        }],
    )
    monkeypatch.setattr(module, "protocol_registry", registry)
    server = FakeMcp()
    module.register_protocol_pattern_tools(server)

    analysis = server.tools["protocol_pattern_analyze_package"]("com.example.chat")

    assert analysis["pattern_count"] == 1
    assert analysis["network_pattern_count"] == 1
    assert analysis["versions"] == ["4.2.1+42001"]
    assert analysis["hosts"] == ["api.example.test"]
    assert analysis["statuses"] == {"observed": 1}
