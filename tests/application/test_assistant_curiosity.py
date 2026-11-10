"""Regression tests for pending curiosity-answer retry semantics."""

from app.application.services.assistant_curiosity import capture_curiosity_answer


class FakeCuriosityEngine:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.context = None

    def execute(self, context):
        self.context = context
        if self.error is not None:
            raise self.error
        return self.result


def test_failed_capture_preserves_pending_need_id():
    engine = FakeCuriosityEngine(result={"success": False, "error": "unsupported action"})

    captured, pending_need_id = capture_curiosity_answer(
        "resposta do usuário",
        "need-123",
        curiosity_engine=engine,
    )

    assert captured is False
    assert pending_need_id == "need-123"
    assert engine.context == {
        "action": "store_answer",
        "need_id": "need-123",
        "user_answer": "resposta do usuário",
    }


def test_capture_exception_preserves_pending_need_id():
    engine = FakeCuriosityEngine(error=RuntimeError("temporary storage failure"))

    captured, pending_need_id = capture_curiosity_answer(
        "resposta do usuário",
        "need-456",
        curiosity_engine=engine,
    )

    assert captured is False
    assert pending_need_id == "need-456"


def test_successful_capture_clears_pending_need_id():
    engine = FakeCuriosityEngine(result={"success": True})

    captured, pending_need_id = capture_curiosity_answer(
        "resposta do usuário",
        "need-789",
        curiosity_engine=engine,
    )

    assert captured is True
    assert pending_need_id is None


def test_missing_pending_need_skips_engine():
    engine = FakeCuriosityEngine(result={"success": True})

    captured, pending_need_id = capture_curiosity_answer(
        "resposta sem pergunta pendente",
        None,
        curiosity_engine=engine,
    )

    assert captured is False
    assert pending_need_id is None
    assert engine.context is None


def test_real_curiosity_engine_rejection_preserves_pending_need_id():
    from app.application.services.curiosity_engine import CuriosityEngine

    engine = CuriosityEngine()

    captured, pending_need_id = capture_curiosity_answer(
        "resposta do usuário",
        "need-real-engine",
        curiosity_engine=engine,
    )

    # The current engine does not implement "store_answer"; failure must not
    # silently discard the pending need. This does not claim answer persistence.
    assert captured is False
    assert pending_need_id == "need-real-engine"
