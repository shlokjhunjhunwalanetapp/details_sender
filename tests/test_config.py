from src.config import _safe_int, _safe_time


def test_safe_int_invalid_uses_default() -> None:
    assert _safe_int("not-a-number", 10, minimum=1) == 10


def test_safe_int_honors_minimum() -> None:
    assert _safe_int("-5", 10, minimum=1) == 1


def test_safe_time_invalid_uses_default() -> None:
    value = _safe_time("99:99", "09:15")
    assert value.hour == 9 and value.minute == 15
