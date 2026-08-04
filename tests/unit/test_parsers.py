"""Offline unit tests for teleboss.shared.parsers (pure / SimpleNamespace fakes)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture(scope="module")
def parsers():
    from teleboss.shared import parsers as mod

    return mod


def test_extract_arg_hit_miss_none(parsers) -> None:
    assert parsers.extract_arg("/ban user reason", 1) == "user"
    assert parsers.extract_arg("/ban", 5) is None
    assert parsers.extract_arg(None, 0) is None  # type: ignore[arg-type]


def test_html_fix_escapes(parsers) -> None:
    assert parsers.html_fix("a&b<c>d") == "a&amp;b&lt;c&gt;d"


def test_time_parser_compound_invalid_bare(parsers) -> None:
    assert parsers.time_parser("1h30m") == 5400
    assert parsers.time_parser("1x") is None
    assert parsers.time_parser("42") == 42


@pytest.mark.parametrize(
    ("seconds", "needle"),
    [
        (0, "0c."),
        (30, "с."),
        (90, "м."),
        (3661, "ч."),
        (90000, "дн."),
    ],
)
def test_formatted_timer_buckets(parsers, seconds: int, needle: str) -> None:
    out = parsers.formatted_timer(seconds)
    assert needle in out
    if seconds == 0:
        assert out == "0c."
    if seconds >= 86400:
        assert out.startswith("1 дн.")


def test_topic_reply_fix(parsers) -> None:
    assert parsers.topic_reply_fix(None) is None
    forum = SimpleNamespace(content_type="forum_topic_created")
    assert parsers.topic_reply_fix(forum) is None
    msg = SimpleNamespace(content_type="text")
    assert parsers.topic_reply_fix(msg) is msg


def test_username_parser_paths(parsers) -> None:
    deleted = SimpleNamespace(
        from_user=SimpleNamespace(first_name="", username=None, last_name=None)
    )
    assert parsers.username_parser(deleted) == "DELETED USER"

    anon = SimpleNamespace(
        from_user=SimpleNamespace(
            first_name="A", username="GroupAnonymousBot", last_name=None
        )
    )
    assert parsers.username_parser(anon) == "ANONYMOUS ADMIN"

    plain = SimpleNamespace(
        from_user=SimpleNamespace(first_name="Ada", username=None, last_name="Lovelace")
    )
    assert parsers.username_parser(plain) == "Ada Lovelace"

    tagged = SimpleNamespace(
        from_user=SimpleNamespace(first_name="Ada", username="ada", last_name=None)
    )
    assert parsers.username_parser(tagged) == "Ada (@ada)"
    assert parsers.username_parser(tagged, html=True) == "Ada (@ada)"

    html_user = SimpleNamespace(
        from_user=SimpleNamespace(first_name="A<B>", username=None, last_name=None)
    )
    assert parsers.username_parser(html_user, html=True) == "A&lt;B&gt;"


def test_username_parser_invite(parsers) -> None:
    msg = SimpleNamespace(
        json={
            "new_chat_participant": {
                "first_name": "Neo",
                "last_name": None,
                "username": "neo",
            }
        }
    )
    assert parsers.username_parser_invite(msg) == "Neo (@neo)"
    assert "&lt;" not in parsers.username_parser_invite(msg, html=True)


def test_username_parser_chat_member(parsers) -> None:
    member = SimpleNamespace(
        user=SimpleNamespace(first_name="Cypher", last_name=None, username="cy")
    )
    assert parsers.username_parser_chat_member(member) == "Cypher (@cy)"
    assert parsers.username_parser_chat_member(member, need_username=False) == "Cypher"
    member_html = SimpleNamespace(
        user=SimpleNamespace(first_name="A&B", last_name=None, username=None)
    )
    assert parsers.username_parser_chat_member(member_html, html=True) == "A&amp;B"
