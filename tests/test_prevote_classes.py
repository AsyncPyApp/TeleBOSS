"""Prevote class map / inheritance / identity (no HEAD AST move-only)."""

from __future__ import annotations

import importlib

from helpers import (
    PREVOTE_DOMAIN_CLASS_MAP,
    PREVOTE_EXPECTED_CLASSES,
    PREVOTE_INHERITANCE,
    REPO_ROOT,
)


def test_expected_map_and_inheritance_colocated() -> None:
    assert len(PREVOTE_EXPECTED_CLASSES) == 28
    mapped = [c for classes in PREVOTE_DOMAIN_CLASS_MAP.values() for c in classes]
    assert len(mapped) == 28 and len(set(mapped)) == 28
    assert set(mapped) == set(PREVOTE_EXPECTED_CLASSES)
    settings = PREVOTE_DOMAIN_CLASS_MAP["teleboss.domain.settings.prevote"]
    assert "Shield" in settings and "Whitelist" in settings
    for child, parent in PREVOTE_INHERITANCE.items():
        same = any(child in classes and parent in classes for classes in PREVOTE_DOMAIN_CLASS_MAP.values())
        assert same, f"{child}/{parent}"


def test_domain_prevote_files_exist() -> None:
    for domain in ("moderation", "settings", "admin", "allies", "content"):
        path = REPO_ROOT / "teleboss" / "domain" / domain / "prevote.py"
        assert path.is_file(), domain


def test_shim_identity_and_inheritance(utils_mod) -> None:
    import prevote

    for name in PREVOTE_EXPECTED_CLASSES:
        assert hasattr(prevote, name), name

    for mod_name, class_names in PREVOTE_DOMAIN_CLASS_MAP.items():
        mod = importlib.import_module(mod_name)
        for name in class_names:
            assert getattr(prevote, name) is getattr(mod, name), name

    assert issubclass(prevote.Kick, prevote.Ban)
    assert issubclass(prevote.MessageSilentRemover, prevote.MessageRemover)
    assert issubclass(prevote.OpGlobal, prevote.Op)
    assert getattr(prevote.Ban, "vote_type", None) == "ban"
