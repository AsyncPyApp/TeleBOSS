"""Offline unit tests for access helpers with mocked bot (no live API)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


def test_allowed_list_locked_and_unlocked(utils_mod) -> None:
    from teleboss.shared.access import allowed_list

    unlocked = allowed_list(locked=False)
    locked = allowed_list(locked=True)
    assert unlocked
    assert locked
    for name, rus in utils_mod.data.admin_rus.items():
        assert rus in unlocked
        assert rus in locked
    # Glyphs: True → ✅; False → ❌ (unlocked) or 🔒 (locked)
    assert "✅" in unlocked or "❌" in unlocked
    assert "🔒" in locked or "✅" in locked


def test_command_forbidden_private_wrong_main(utils_mod, monkeypatch) -> None:
    from teleboss.shared import access as access_mod

    replies: list = []

    def _reply(message, text):  # noqa: ANN001
        replies.append(text)
        return MagicMock()

    monkeypatch.setattr(access_mod.bot, "reply_to", _reply)

    private = SimpleNamespace(
        chat=SimpleNamespace(id=42),
        from_user=SimpleNamespace(id=42),
    )
    assert access_mod.command_forbidden(private, not_in_private_dialog=True) is True
    assert replies and "личных" in replies[-1]

    replies.clear()
    not_private = SimpleNamespace(
        chat=SimpleNamespace(id=99),
        from_user=SimpleNamespace(id=42),
    )
    assert access_mod.command_forbidden(not_private, not_in_private_dialog=True) is False

    wrong_chat = SimpleNamespace(
        chat=SimpleNamespace(id=999),
        from_user=SimpleNamespace(id=42),
    )
    assert access_mod.command_forbidden(wrong_chat) is True
    assert replies and "основном чате" in replies[-1]

    main = SimpleNamespace(
        chat=SimpleNamespace(id=utils_mod.data.main_chat_id),
        from_user=SimpleNamespace(id=42),
    )
    assert access_mod.command_forbidden(main) is None


def test_bot_name_checker_mention_and_gate(utils_mod, monkeypatch) -> None:
    from teleboss.shared import access as access_mod

    # Init-mode smoke sets main_chat_id=-1; set a real chat so get_chat=False path proceeds.
    monkeypatch.setattr(access_mod.data, "main_chat_id", -100123)
    me = SimpleNamespace(username="TeleBossBot")
    monkeypatch.setattr(access_mod.bot, "get_me", lambda: me)

    bare = SimpleNamespace(text="/ban")
    assert access_mod.bot_name_checker(bare) is True

    self_mention = SimpleNamespace(text="/ban@TeleBossBot")
    assert access_mod.bot_name_checker(self_mention) is True

    other = SimpleNamespace(text="/ban@OtherBot")
    assert access_mod.bot_name_checker(other) is False

    # get_chat gate: when main is set, get_chat=True returns False early.
    assert access_mod.bot_name_checker(bare, get_chat=True) is False

    no_text = SimpleNamespace(text=None)
    assert access_mod.bot_name_checker(no_text) is True


def test_welcome_msg_get_missing_and_empty(utils_mod, tmp_path, monkeypatch) -> None:
    from teleboss.shared import access as access_mod

    path = str(tmp_path).replace("\\", "/") + "/"
    monkeypatch.setattr(access_mod.data, "path", path)
    message = SimpleNamespace(chat=SimpleNamespace(title="SmokeChat"))

    missing = access_mod.welcome_msg_get("User", message)
    assert missing == access_mod.data.welcome_default.format("User", "SmokeChat")

    welcome = tmp_path / "welcome.txt"
    welcome.write_text("", encoding="utf-8")
    empty = access_mod.welcome_msg_get("User", message)
    assert empty == access_mod.data.welcome_default.format("User", "SmokeChat")

    welcome.write_text("{0} hi {1}", encoding="utf-8")
    custom = access_mod.welcome_msg_get("User", message)
    assert custom == "User hi SmokeChat"
