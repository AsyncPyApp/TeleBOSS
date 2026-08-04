"""Offline unit tests for calc_engine via queue.Queue (no multiprocessing spawn)."""

from __future__ import annotations

import queue


def test_calc_engine_ok_divzero_syntax_power_decimal(teleboss_runtime) -> None:
    from teleboss.shared.calc import calc_engine

    q: queue.Queue = queue.Queue()

    calc_engine("2+2", q)
    assert "<code>4</code>" in q.get_nowait()

    calc_engine("1/0", q)
    assert "деление на 0" in q.get_nowait()

    calc_engine("2+", q)
    assert "Неверно введено" in q.get_nowait()

    calc_engine("2^3", q)
    assert "<code>8</code>" in q.get_nowait()

    calc_engine("1,5+1,5", q)
    out = q.get_nowait()
    assert "<code>" in out
    assert "3" in out
