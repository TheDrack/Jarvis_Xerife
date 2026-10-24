from app.application.services.curiosity_intake import CuriosityIntake


def test_capture_creates_evidence_aware_discovery_card(tmp_path):
    intake = CuriosityIntake(storage_path=str(tmp_path / "inbox.jsonl"))
    result = intake.execute({
        "action": "capture",
        "source_type": "research",
        "source_title": "A new scheduling approach",
        "source_uri": "https://example.test/paper",
        "observation": "The paper proposes adaptive queue scheduling.",
        "user_benefit": "Could reduce wait time for the user's multi-agent jobs.",
        "connections": ["multi-agent queue"],
    })

    assert result["success"] is True
    assert result["duplicate"] is False
    record = result["record"]
    assert record["evidence_level"] == "unverified"
    assert record["status"] == "captured"
    assert record["user_benefit"].startswith("Could reduce")
    assert record["open_questions"]
    assert (tmp_path / "inbox.jsonl").is_file()


def test_capture_deduplicates_same_discovery(tmp_path):
    intake = CuriosityIntake(storage_path=str(tmp_path / "inbox.jsonl"))
    payload = {
        "source_type": "news",
        "source_title": "New model architecture",
        "source_uri": "https://example.test/news",
        "observation": "A new model architecture was announced.",
    }

    first = intake.execute(payload)
    second = intake.execute(payload)

    assert first["success"] is True
    assert first["duplicate"] is False
    assert second["success"] is True
    assert second["duplicate"] is True
    assert len(intake.execute({"action": "list_recent"})["records"]) == 1


def test_capture_requires_source_title_or_observation(tmp_path):
    intake = CuriosityIntake(storage_path=str(tmp_path / "inbox.jsonl"))
    result = intake.execute({"action": "capture"})

    assert result["success"] is False
    assert not (tmp_path / "inbox.jsonl").exists()


def test_capture_rejects_unknown_actions(tmp_path):
    intake = CuriosityIntake(storage_path=str(tmp_path / "inbox.jsonl"))
    result = intake.execute({"action": "mutate_repository"})

    assert result["success"] is False
    assert not (tmp_path / "inbox.jsonl").exists()
