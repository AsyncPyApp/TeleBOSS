"""Offline pure vote_ui helpers (get_hash, make_keyboard) — no Bot API."""

from __future__ import annotations

from telebot import types


def test_get_hash_user_votes_passthrough_and_pbkdf(teleboss_runtime) -> None:
    from teleboss.shared.vote_ui import get_hash

    with_list = [{"button_type": "user_votes", "name": "Список голосов"}]
    assert get_hash("uid-42", "chat-inst", with_list) == "uid-42"

    private = [{"button_type": "my_vote", "name": "Узнать мой голос"}]
    h1 = get_hash(123, "chat-inst", private)
    h2 = get_hash(123, "chat-inst", private)
    h3 = get_hash(123, "other-inst", private)
    assert isinstance(h1, str) and len(h1) == 32
    assert h1 == h2
    assert h1 != h3


def test_make_keyboard_vote_counts_and_hidden(teleboss_runtime) -> None:
    from teleboss.shared.vote_ui import make_keyboard

    scheme = [
        {"button_type": "vote!_Да", "name": "Да", "user_list": ["a", "b"]},
        {"button_type": "vote!_Нет", "name": "Нет", "user_list": []},
        {"button_type": "my_vote", "name": "Узнать мой голос"},
        {"button_type": "cancel", "name": "Отмена голосования", "user_id": 1},
    ]
    shown = make_keyboard(scheme, hidden=False)
    assert isinstance(shown, types.InlineKeyboardMarkup)
    flat = [b for row in shown.keyboard for b in row]
    texts = [b.text for b in flat]
    assert any(t.startswith("Да") and "2" in t for t in texts)
    assert any(t == "Узнать мой голос" for t in texts)

    hidden = make_keyboard(scheme, hidden=True)
    hidden_texts = [b.text for row in hidden.keyboard for b in row]
    assert "Да" in hidden_texts
    assert not any(" - " in t and t.startswith("Да") for t in hidden_texts)
