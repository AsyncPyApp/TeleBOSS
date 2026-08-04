"""Prevote stable class-level vote_type ↔ postvote registry keys."""

from __future__ import annotations

# Class-level vote_type only (skip Title/Avatar/Allies/Rules/PrivateMode/Timer/Votes
# dynamic assignments documented as residual offline).
STABLE_VOTE_TYPES = {
    "Ban": "ban",
    "Mute": "ban",
    "Kick": "ban",
    "Unban": "unban",
    "MessageRemover": "delete message",
    "MessageSilentRemover": "delete message",
    "NewUserChecker": "captcha",
    "Thresholds": "threshold",
    "Rating": "change rate",
    "Whitelist": "whitelist",
    "Shield": "shield",
    "Marmalade": "marmalade",
    "OpSetup": "op setup",
    "Op": "op",
    "OpGlobal": "global op permissions",
    "RemoveTopic": "remove topic",
    "Rank": "rank",
    "Deop": "deop",
    "CustomPoll": "custom poll",
}


def test_stable_prevote_vote_types_in_registry(poll_engine_snapshot) -> None:
    import postvote
    import prevote

    PollEngine = poll_engine_snapshot["PollEngine"]
    postvote.post_vote_list_init()

    assert len(STABLE_VOTE_TYPES) >= 10
    for cls_name, expected in STABLE_VOTE_TYPES.items():
        cls = getattr(prevote, cls_name)
        assert getattr(cls, "vote_type", None) == expected, cls_name
        assert expected in PollEngine.post_vote_list, f"{cls_name} → {expected!r}"
