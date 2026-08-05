"""Postvote registry runtime: key → PostVote instance → non-empty description."""

from __future__ import annotations

from helpers import POSTVOTE_EXPECTED_KEYS


def test_registry_runtime_key_instance_description(poll_engine_snapshot) -> None:
    from teleboss.domain import postvote_registry
    from teleboss.voting.bases import PostVote

    PollEngine = poll_engine_snapshot["PollEngine"]
    dict_id_before = id(PollEngine.post_vote_list)
    sentinel = object()
    PollEngine.post_vote_list["_t03_sentinel"] = sentinel  # type: ignore[index]

    postvote_registry.post_vote_list_init()

    assert id(PollEngine.post_vote_list) == dict_id_before
    assert PollEngine.post_vote_list.get("_t03_sentinel") is sentinel

    for key in POSTVOTE_EXPECTED_KEYS:
        assert key in PollEngine.post_vote_list, key
        inst = PollEngine.post_vote_list[key]
        assert isinstance(inst, PostVote), f"{key}: {type(inst)}"
        desc = inst.description
        assert isinstance(desc, str) and desc.strip(), f"{key}: empty description"
        assert desc == type(inst)._description, key

    # Second init preserves identity + sentinel (no rebinding).
    postvote_registry.post_vote_list_init()
    assert id(PollEngine.post_vote_list) == dict_id_before
    assert PollEngine.post_vote_list.get("_t03_sentinel") is sentinel
    del PollEngine.post_vote_list["_t03_sentinel"]
