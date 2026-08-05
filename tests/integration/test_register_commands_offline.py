"""Offline register_commands handler-count delta + PreVote buttons / abuse timer."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_register_commands_offline_delta(runtime_bot) -> None:
    """Assert built-in registration raises message_handler count; restore list after."""
    import main  # noqa: F401 — ensure baseline side-effect handlers exist
    from teleboss.app.commands import BuildInCommands
    from teleboss.shared.bootstrap import register_commands

    baseline = list(runtime_bot.message_handlers)
    cmds = BuildInCommands().built_in_commands_dict
    register_commands({}, cmds)
    try:
        assert len(runtime_bot.message_handlers) == len(baseline) + len(cmds)
        # Plugins-first order preserved in source (static); empty plugins → only built-ins.
        last = runtime_bot.message_handlers[-1]
        filters = last.get("filters") or {}
        assert "commands" in filters
    finally:
        runtime_bot.message_handlers[:] = baseline
        assert list(runtime_bot.message_handlers) == baseline


def test_prevote_get_buttons_scheme_privacy_matrix(runtime_data, monkeypatch) -> None:
    from teleboss.voting.bases import PreVote

    monkeypatch.setattr(runtime_data, "bot_id", 999001)
    anon = runtime_data.ANONYMOUS_ID
    user_id = 424242

    for privacy, list_btn in (
        ("public", "user_votes"),
        ("private", "my_vote"),
        ("hidden", "my_vote"),
    ):
        inst = object.__new__(PreVote)
        inst.privacy = privacy
        inst.user_id = user_id
        scheme = PreVote.get_buttons_scheme(inst)
        types_ = [b["button_type"] for b in scheme]
        assert types_[0] == "vote!_Да" and types_[1] == "vote!_Нет"
        assert list_btn in types_
        assert "cancel" in types_
        cancel = next(b for b in scheme if b["button_type"] == "cancel")
        assert cancel["user_id"] == user_id

    # Bot / anonymous initiator → no cancel.
    for uid in (runtime_data.bot_id, anon):
        inst = object.__new__(PreVote)
        inst.privacy = "private"
        inst.user_id = uid
        types_ = [b["button_type"] for b in PreVote.get_buttons_scheme(inst)]
        assert "cancel" not in types_


def test_poll_engine_get_abuse_timer(runtime_bot, runtime_data, monkeypatch) -> None:
    from teleboss.voting.engine import poll_engine

    answered: list = []

    def _answer(**kwargs):  # noqa: ANN003
        answered.append(kwargs)
        return MagicMock()

    monkeypatch.setattr(runtime_bot, "answer_callback_query", _answer)
    # Smoke init sets wait_timer=0 in debug; restore a real cooldown for this probe.
    monkeypatch.setattr(runtime_data, "wait_timer", 30)

    call = SimpleNamespace(
        id="cb-1",
        message=SimpleNamespace(id=77),
        from_user=SimpleNamespace(id=55),
    )
    key = f"{call.message.id}.{call.from_user.id}"
    poll_engine.vote_abuse.pop(key, None)

    assert poll_engine.get_abuse_timer(call) is None

    poll_engine.vote_abuse[key] = int(time.time())
    assert poll_engine.get_abuse_timer(call) is True
    assert answered and "Пожалуйста" in answered[-1]["text"]

    poll_engine.vote_abuse[key] = int(time.time()) - 100
    assert poll_engine.get_abuse_timer(call) is False
    assert key not in poll_engine.vote_abuse
