from app.application.return_activity_service import ReturnActivityDetector


def test_no_greeting_during_normal_activity():
    detector = ReturnActivityDetector(idle_threshold_seconds=10)
    assert detector.observe(0) is False
    assert detector.observe(4) is False
    assert detector.observe(9.9) is False


def test_greets_once_when_activity_returns_after_idle():
    detector = ReturnActivityDetector(idle_threshold_seconds=10)
    assert detector.observe(10) is False
    assert detector.observe(40) is False
    assert detector.observe(0) is True
    assert detector.observe(0.5) is False


def test_each_idle_cycle_can_trigger_one_greeting():
    detector = ReturnActivityDetector(idle_threshold_seconds=10)
    assert detector.observe(11) is False
    assert detector.observe(1) is True
    assert detector.observe(12) is False
    assert detector.observe(2) is True


def test_threshold_must_be_positive():
    try:
        ReturnActivityDetector(idle_threshold_seconds=0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_negative_idle_value_is_rejected():
    detector = ReturnActivityDetector(idle_threshold_seconds=10)
    try:
        detector.observe(-1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
