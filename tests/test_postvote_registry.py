"""Postvote registry / class / key parity offline."""

from __future__ import annotations

import importlib

from helpers import (
    POSTVOTE_DOMAIN_CLASS_MAP,
    POSTVOTE_EXPECTED_CLASSES,
    POSTVOTE_EXPECTED_KEYS,
    extract_postvote_registry_keys,
)
from helpers import REPO_ROOT


def test_expected_counts() -> None:
    assert len(POSTVOTE_EXPECTED_CLASSES) == 30
    assert len(POSTVOTE_EXPECTED_KEYS) == 30
    mapped = [c for classes in POSTVOTE_DOMAIN_CLASS_MAP.values() for c in classes]
    assert len(mapped) == 30 and len(set(mapped)) == 30
    assert set(mapped) == set(POSTVOTE_EXPECTED_CLASSES)


def test_domain_exports_and_registry_init_symbol(teleboss_runtime) -> None:
    from teleboss.domain import postvote_registry

    for mod_name, names in POSTVOTE_DOMAIN_CLASS_MAP.items():
        mod = importlib.import_module(mod_name)
        for name in names:
            assert hasattr(mod, name), f"{mod_name}.{name}"
    assert callable(postvote_registry.post_vote_list_init)


def test_domain_class_counts() -> None:
    for mod_name, names in POSTVOTE_DOMAIN_CLASS_MAP.items():
        mod = importlib.import_module(mod_name)
        found = [
            n
            for n, obj in vars(mod).items()
            if isinstance(obj, type) and obj.__module__ == mod_name
        ]
        assert set(found) == set(names), f"{mod_name}: found={found}"


def test_registry_keys_and_update_source() -> None:
    reg_keys = extract_postvote_registry_keys()
    assert len(reg_keys) == 30
    assert reg_keys == POSTVOTE_EXPECTED_KEYS
    reg_src = (REPO_ROOT / "src/domain/postvote_registry.py").read_text(encoding="utf-8")
    assert "PollEngine.post_vote_list.update(" in reg_src
    assert "PollEngine.post_vote_list =" not in reg_src.replace(
        "PollEngine.post_vote_list.update", ""
    )


def test_init_preserves_dict_identity_and_keys(poll_engine_snapshot) -> None:
    from teleboss.domain import postvote_registry

    PollEngine = poll_engine_snapshot["PollEngine"]
    dict_id_before = id(PollEngine.post_vote_list)
    sentinel = object()
    PollEngine.post_vote_list["_sentinel"] = sentinel  # type: ignore[index]
    postvote_registry.post_vote_list_init()
    assert id(PollEngine.post_vote_list) == dict_id_before
    assert PollEngine.post_vote_list.get("_sentinel") is sentinel
    assert all(k in PollEngine.post_vote_list for k in POSTVOTE_EXPECTED_KEYS)
    del PollEngine.post_vote_list["_sentinel"]
    assert len([k for k in POSTVOTE_EXPECTED_KEYS if k in PollEngine.post_vote_list]) == 30
