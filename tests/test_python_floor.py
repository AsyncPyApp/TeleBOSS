"""Runtime Python floor gate (stdlib leaf)."""

from __future__ import annotations

import pytest

from teleboss.shared.python_floor import MIN_PYTHON, ensure_min_python


def test_min_python_constant() -> None:
    assert MIN_PYTHON == (3, 14, 6)


def test_ensure_min_python_passes_on_current() -> None:
    ensure_min_python()  # must not raise / exit on suite interpreter


def test_ensure_min_python_fails_closed_below_floor(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        ensure_min_python((3, 14, 5))
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "3.14.6+" in err
    assert "3.14.5" in err


def test_ensure_min_python_passes_at_and_above_floor() -> None:
    ensure_min_python((3, 14, 6))
    ensure_min_python((3, 15, 0))
