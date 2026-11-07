"""Dry-run validation must stop before artifact export or PR publication."""
from app.application.services.evolution_orchestrator import EvolutionOrchestrator


def test_dry_run_returns_only_after_gatekeeper_validates_candidate(monkeypatch):
    orchestrator = EvolutionOrchestrator()
    monkeypatch.setenv("EVOLUTION_ENABLED", "true")

    class Gatekeeper:
        def __init__(self):
            self.proposals = []

        def approve_evolution(self, proposal):
            self.proposals.append(proposal)
            return True, "approved"

    gatekeeper = Gatekeeper()
    monkeypatch.setattr(orchestrator, "_load_meta_reflection", lambda: {})
    monkeypatch.setattr(orchestrator, "_get_snapshot", lambda: "snapshot")
    monkeypatch.setattr(orchestrator, "_get_consolidated_context", lambda: "")
    monkeypatch.setattr(orchestrator, "_read_context", lambda: {})
    monkeypatch.setattr(orchestrator, "_get_gatekeeper", lambda: gatekeeper)
    monkeypatch.setattr(orchestrator, "_search_procedural_memory", lambda _: None)
    monkeypatch.setattr(orchestrator, "_build_prompt", lambda *args: "prompt")
    monkeypatch.setattr(orchestrator, "_call_llm", lambda _: "def candidate(): return True")
    monkeypatch.setattr(orchestrator, "_validate_syntax", lambda _: True)
    monkeypatch.setattr(
        orchestrator, "_extract_code", lambda response: response
    )
    monkeypatch.setattr(orchestrator, "_log_thought", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator, "_increment_metabolism", lambda: None)
    monkeypatch.setattr(
        orchestrator,
        "_export_validated_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not export")),
    )

    result = orchestrator.execute(
        {
            "cap_id": "CAP-058",
            "cap_title": "Adapt execution plans",
            "mission_id": "dry-run-058",
            "target_file": "app/application/services/task_runner.py",
            "dry_run": True,
        }
    )

    assert result["success"] is True, result
    assert result["validated"] is True
    assert result["dry_run"] is True
    assert result["publication_deferred"] is True
    assert result["target_file"] == "app/application/services/task_runner.py"
    assert len(gatekeeper.proposals) == 2
    assert gatekeeper.proposals[0]["files_modified"] == [
        "app/application/services/task_runner.py"
    ]
    assert gatekeeper.proposals[1]["proposed_code"] == "def candidate(): return True"


def test_cooperative_cancel_after_llm_stops_before_candidate_validation(monkeypatch):
    import threading

    orchestrator = EvolutionOrchestrator()
    monkeypatch.setenv("EVOLUTION_ENABLED", "true")
    cancel_event = threading.Event()

    class Gatekeeper:
        def __init__(self):
            self.proposals = []

        def approve_evolution(self, proposal):
            self.proposals.append(proposal)
            return True, "approved"

    gatekeeper = Gatekeeper()
    monkeypatch.setattr(orchestrator, "_load_meta_reflection", lambda: {})
    monkeypatch.setattr(orchestrator, "_get_snapshot", lambda: {})
    monkeypatch.setattr(orchestrator, "_get_consolidated_context", lambda: "")
    monkeypatch.setattr(orchestrator, "_read_context", lambda: {})
    monkeypatch.setattr(orchestrator, "_get_gatekeeper", lambda: gatekeeper)
    monkeypatch.setattr(orchestrator, "_search_procedural_memory", lambda _: None)
    monkeypatch.setattr(orchestrator, "_build_prompt", lambda *args: "prompt")

    def cancel_during_llm(_prompt):
        cancel_event.set()
        return "def candidate(): return True"

    monkeypatch.setattr(orchestrator, "_call_llm", cancel_during_llm)
    monkeypatch.setattr(orchestrator, "_log_thought", lambda *args, **kwargs: None)

    result = orchestrator.execute(
        {
            "cap_id": "CAP-058",
            "mission_id": "cancel-058",
            "target_file": "app/application/services/task_runner.py",
            "_cancel_event": cancel_event,
        }
    )

    assert result["success"] is False
    assert result["reason"] == "cancelled"
    assert len(gatekeeper.proposals) == 1
