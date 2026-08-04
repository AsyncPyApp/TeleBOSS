"""Soft VERSION / MIN_VERSION checks (no hard pins)."""

from __future__ import annotations

from helpers import assert_soft_version_order


def test_soft_version_presence_and_order(runtime_data) -> None:
    assert_soft_version_order(runtime_data.MIN_VERSION, runtime_data.VERSION)
    assert isinstance(runtime_data.BUILD_DATE, str) and runtime_data.BUILD_DATE.strip()
    assert isinstance(runtime_data.CODENAME, str) and runtime_data.CODENAME.strip()


def test_chat_id_init_smoke(runtime_data) -> None:
    assert runtime_data.main_chat_id == -1
    assert runtime_data.debug is True
