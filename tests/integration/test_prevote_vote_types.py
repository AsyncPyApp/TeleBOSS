"""Prevote stable class-level vote_type ↔ postvote registry keys."""

from __future__ import annotations

import importlib

from helpers import PREVOTE_DOMAIN_CLASS_MAP, STABLE_VOTE_TYPES


def test_stable_prevote_vote_types_in_registry(poll_engine_snapshot) -> None:
    from teleboss.domain import postvote_registry

    PollEngine = poll_engine_snapshot["PollEngine"]
    postvote_registry.post_vote_list_init()

    assert len(STABLE_VOTE_TYPES) >= 10
    for cls_name, expected in STABLE_VOTE_TYPES.items():
        cls = None
        for mod_name, class_names in PREVOTE_DOMAIN_CLASS_MAP.items():
            if cls_name in class_names:
                cls = getattr(importlib.import_module(mod_name), cls_name)
                break
        assert cls is not None, cls_name
        assert getattr(cls, "vote_type", None) == expected, cls_name
        assert expected in PollEngine.post_vote_list, f"{cls_name} → {expected!r}"
