from app.adapters.edge.navigation_gps import NavigationGraph


def test_plans_lowest_expected_cost_and_exposes_backend(tmp_path):
    graph = NavigationGraph(tmp_path / "navigation.sqlite3", reliability_penalty=2.0)
    graph.upsert_node("home", label="Home")
    graph.upsert_node("settings", label="Settings")
    graph.upsert_node("target", label="Target")

    graph.record_transition(
        "home", "target", action="open_target", backend="visual_template",
        latency_seconds=0.1, success=False,
    )
    for _ in range(5):
        graph.record_transition(
            "home", "target", action="open_target", backend="visual_template",
            latency_seconds=0.1, success=False,
        )
    graph.record_transition(
        "home", "settings", action="open_settings", backend="accessibility",
        latency_seconds=0.2, success=True,
    )
    graph.record_transition(
        "settings", "target", action="select_target", backend="dom",
        latency_seconds=0.2, success=True,
    )

    route = graph.plan("home", "target")
    assert route is not None
    assert route.nodes == ("home", "settings", "target")
    assert [step.backend for step in route.steps] == ["accessibility", "dom"]
    assert route.total_cost > 0
    graph.close()


def test_returns_none_for_unknown_or_unreachable_nodes():
    graph = NavigationGraph()
    graph.upsert_node("known")
    graph.upsert_node("isolated")
    assert graph.plan("missing", "known") is None
    assert graph.plan("known", "isolated") is None
    graph.close()


def test_same_node_is_zero_step_route():
    graph = NavigationGraph()
    graph.upsert_node("current")
    route = graph.plan("current", "current")
    assert route is not None
    assert route.steps == ()
    assert route.total_cost == 0
    graph.close()


def test_transition_metrics_and_metadata_persist(tmp_path):
    path = tmp_path / "navigation.sqlite3"
    graph = NavigationGraph(path)
    graph.record_transition(
        "a", "b", action="click_save", backend="uia",
        latency_seconds=0.4, success=True,
        metadata={"target_name": "Save", "postcondition": "Saved"},
    )
    graph.record_transition(
        "a", "b", action="click_save", backend="uia",
        latency_seconds=0.8, success=False,
    )
    before = graph.snapshot()
    assert before["edges"][0]["attempts"] == 2
    assert before["edges"][0]["successes"] == 1
    assert before["edges"][0]["failures"] == 1
    assert before["edges"][0]["metadata"]["target_name"] == "Save"
    graph.close()

    reopened = NavigationGraph(path)
    after = reopened.snapshot()
    assert after["edges"][0]["attempts"] == 2
    assert after["edges"][0]["last_latency"] == 0.8
    reopened.close()


def test_rejects_invalid_metrics_and_identifiers():
    graph = NavigationGraph()
    try:
        graph.upsert_node(" ")
    except ValueError:
        pass
    else:
        raise AssertionError("blank node IDs must be rejected")

    try:
        graph.record_transition(
            "a", "b", action="click", backend="uia",
            latency_seconds=-1, success=True,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("negative latency must be rejected")
    graph.close()
