"""Assert root compatibility shims are gone (post-T05)."""

from __future__ import annotations

import importlib.util

from helpers import REPO_ROOT, SHIM_MODS


def test_root_shim_files_absent() -> None:
    assert len(SHIM_MODS) == 6
    for name in SHIM_MODS:
        path = REPO_ROOT / f"{name}.py"
        assert not path.exists(), f"root shim still present: {path.name}"


def test_root_shim_find_spec_is_none() -> None:
    for name in SHIM_MODS:
        assert importlib.util.find_spec(name) is None, name


def test_root_shim_import_fails() -> None:
    for name in SHIM_MODS:
        try:
            __import__(name)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"unexpected successful import of banned module {name!r}")
