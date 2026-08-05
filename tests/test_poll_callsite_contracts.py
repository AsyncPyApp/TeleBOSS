"""Call-site contracts for chat-aware poll lookup and atomic vote mutation (T03)."""

from __future__ import annotations

import ast
import json
import time
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

from helpers import REPO_ROOT
from teleboss.shared.storage.sql_worker import ApplyVoteResult, ApplyVoteStatus


@pytest.fixture(autouse=True)
def _lock_callback_handler_order(teleboss_runtime) -> None:
    """Import ``main`` before handler modules so callback registration order is stable.

    Importing ``votes``/``op`` first would register those callbacks before captcha/help
    and break ``CALLBACK_PROBE_ORDER`` probes for the rest of the session.
    """
    import main  # noqa: F401


# Migrated product callers (T03). Compatibility wrappers live only in sql_worker.
_MIGRATED_CALLERS: tuple[str, ...] = (
    "src/app/handlers/votes.py",
    "src/app/handlers/op.py",
    "src/app/host_commands/membership.py",
    "src/app/host_commands/info.py",
    "src/app/host_commands/moderation.py",
    "src/app/host_commands/misc.py",
    "src/app/host_commands/__init__.py",
    "src/voting/bases.py",
    "src/voting/engine.py",
    "src/domain/moderation/prevote_join.py",
    "src/domain/admin/prevote_op.py",
    "src/domain/moderation/prevote_messages.py",
)

_LEGACY_FORBIDDEN = frozenset({"get_poll", "update_poll_votes"})
_ALLOWED_LEGACY_CLEANUP = frozenset({"rem_rec"})

_MSG_ID = 4242
_CHAT_A = -10001
_CHAT_B = -10002


def _buttons(*names: str, votes: dict[str, list] | None = None) -> str:
    """Build minimal vote buttons JSON."""
    votes = votes or {}
    scheme = [
        {
            "button_type": f"vote!_{name}",
            "name": name,
            "user_list": list(votes.get(name, [])),
        }
        for name in names
    ]
    return json.dumps(scheme)


def _row(
    unique_id: str,
    message_id: int,
    chat_id: int,
    *,
    poll_type: str = "ban",
    buttons: str | None = None,
    timer: int | None = None,
    votes_need: int = 99,
    hidden: int = 0,
    state: str = "open",
    data: str = "[]",
) -> tuple:
    """Build an 11-field poll row matching SqlWorker offsets."""
    return (
        unique_id,
        message_id,
        poll_type,
        chat_id,
        buttons if buttons is not None else _buttons("yes", "no"),
        timer if timer is not None else int(time.time()) + 3600,
        data,
        votes_need,
        hidden,
        None,
        state,
    )


class FakePollRepository:
    """In-memory T01/T02 poll contracts used by migrated call sites."""

    def __init__(self) -> None:
        self.by_unique: dict[str, tuple] = {}
        self.calls: list[tuple[str, tuple, dict]] = []

    def seed(self, *rows: tuple) -> None:
        """Insert poll rows keyed by ``unique_id``."""
        for row in rows:
            self.by_unique[row[0]] = row

    def _record(self, name: str, args: tuple, kwargs: dict | None = None) -> None:
        self.calls.append((name, args, kwargs or {}))

    def get_open_poll(self, chat_id: int, message_id: int) -> list[tuple]:
        """Composite open lookup — never cross-resolves other chats."""
        self._record("get_open_poll", (chat_id, message_id))
        for row in self.by_unique.values():
            if row[3] == chat_id and row[1] == message_id and row[10] == "open":
                return [row]
        return []

    def get_poll_by_unique_id(self, unique_id: str) -> list[tuple]:
        """Logical lookup for duplicates / timer / recovery."""
        self._record("get_poll_by_unique_id", (unique_id,))
        row = self.by_unique.get(unique_id)
        return [row] if row is not None else []

    def get_recoverable_polls(self) -> list[tuple]:
        self._record("get_recoverable_polls", ())
        return [
            r
            for r in self.by_unique.values()
            if r[10] in ("open", "completing", "failed")
        ]

    def apply_vote(
        self,
        chat_id: int,
        message_id: int,
        mutator: Callable[[tuple], str],
        *,
        busy_timeout: float = 5.0,
    ) -> ApplyVoteResult:
        """Local atomic-ish mutator; mirrors T01 status outcomes."""
        self._record("apply_vote", (chat_id, message_id), {"busy_timeout": busy_timeout})
        rows = [
            r
            for r in self.by_unique.values()
            if r[3] == chat_id and r[1] == message_id
        ]
        if not rows:
            return ApplyVoteResult(ApplyVoteStatus.NOT_FOUND)
        poll = rows[0]
        if poll[10] != "open":
            return ApplyVoteResult(ApplyVoteStatus.NOT_OPEN)
        try:
            new_buttons = mutator(poll)
            if not isinstance(new_buttons, str):
                raise TypeError("mutator must return str")
            updated = poll[:4] + (new_buttons,) + poll[5:]
            self.by_unique[poll[0]] = updated
            return ApplyVoteResult(ApplyVoteStatus.OK, updated)
        except Exception:
            return ApplyVoteResult(ApplyVoteStatus.FAILED)

    def rem_rec(self, unique_id: str) -> None:
        """Allowed interim cleanup (author cancel / expired duplicate)."""
        self._record("rem_rec", (unique_id,))
        self.by_unique.pop(unique_id, None)

    def captcha(self, *_args: Any, **_kwargs: Any) -> Any:
        """Captcha table is out of T03 scope — always clear."""
        self._record("captcha", _args, _kwargs)
        return None

    def get_poll(self, message_id: int) -> list[tuple]:
        """Legacy API — must not be invoked by migrated callers."""
        self._record("get_poll", (message_id,))
        raise AssertionError("migrated callers must not use get_poll")

    def update_poll_votes(self, unique_id: str, buttons_scheme: str) -> None:
        """Legacy API — must not be invoked by migrated callers."""
        self._record("update_poll_votes", (unique_id, buttons_scheme))
        raise AssertionError("migrated callers must not use update_poll_votes")


def _attr_call_names(tree: ast.AST) -> set[str]:
    """Collect ``obj.attr(...)`` attribute names from Call nodes."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _make_callback(
    *,
    chat_id: int,
    message_id: int,
    data: str,
    user_id: int = 7,
    text: str = "Тема голосования",
) -> MagicMock:
    """Build a minimal callback_query-like object."""
    call = MagicMock()
    call.data = data
    call.id = "cq-1"
    call.chat_instance = "chat-inst"
    call.from_user.id = user_id
    call.message.chat.id = chat_id
    call.message.id = message_id
    call.message.message_id = message_id
    call.message.text = text
    return call


def _member_ok(bot: MagicMock) -> None:
    member = MagicMock()
    member.status = "member"
    bot.get_chat_member.return_value = member
    bot.get_chat_member_count.return_value = 50


# ---------------------------------------------------------------------------
# AST / source gates
# ---------------------------------------------------------------------------


def test_migrated_callers_forbid_legacy_get_poll_and_update_poll_votes() -> None:
    """Product callers must not invoke legacy message-only lookup/update."""
    offenders: list[str] = []
    for rel in _MIGRATED_CALLERS:
        path = REPO_ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name in _attr_call_names(tree) & _LEGACY_FORBIDDEN:
            offenders.append(f"{rel}:{name}")
    assert not offenders, offenders


def _sql_worker_public_method_names() -> set[str]:
    """Collect SqlWorker callable names across facade + mixin MRO (AST).

    ``SqlWorker`` is composed from mixins under ``src/shared/storage/``;
    method bodies no longer all live in the facade module.
    """
    storage_dir = REPO_ROOT / "src/shared/storage"
    class_methods: dict[str, set[str]] = {}
    for path in storage_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_methods[node.name] = {
                    n.name
                    for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
    facade = REPO_ROOT / "src/shared/storage/sql_worker.py"
    tree = ast.parse(facade.read_text(encoding="utf-8"))
    sql_worker_bases: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "SqlWorker":
            for base in node.bases:
                if isinstance(base, ast.Name):
                    sql_worker_bases.append(base.id)
            break
    methods = set(class_methods.get("SqlWorker", ()))
    for base_name in sql_worker_bases:
        methods |= class_methods.get(base_name, set())
    return methods


def test_sql_worker_still_defines_legacy_wrappers() -> None:
    """Compatibility methods remain on composed SqlWorker (facade + mixins)."""
    methods = _sql_worker_public_method_names()
    assert "get_poll" in methods
    assert "update_poll_votes" in methods
    assert "get_open_poll" in methods
    assert "apply_vote" in methods
    assert "get_poll_by_unique_id" in methods


def test_sql_worker_composed_methods_via_introspection() -> None:
    """Runtime MRO exposes the same host-facing poll APIs as before the split."""
    from teleboss.shared.storage.sql_worker import SqlWorker

    for name in (
        "get_poll",
        "update_poll_votes",
        "get_open_poll",
        "apply_vote",
        "get_poll_by_unique_id",
        "claim_completion",
        "mark_completed",
        "mark_failed",
        "requeue_for_retry",
        "delete_completed",
        "get_recoverable_polls",
        "add_poll",
        "rem_rec",
        "params",
        "captcha",
    ):
        assert callable(getattr(SqlWorker, name, None)), name


def test_migrated_callers_may_use_rem_rec_for_cleanup() -> None:
    """Author-cancel / expired-duplicate cleanup may still call rem_rec."""
    found: set[str] = set()
    for rel in _MIGRATED_CALLERS:
        path = REPO_ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _attr_call_names(tree) & _ALLOWED_LEGACY_CLEANUP:
            found.add(rel)
    # At least cancel + duplicate paths keep rem_rec (task permits).
    assert "src/app/handlers/votes.py" in found
    assert "src/voting/bases.py" in found


def test_displayed_poll_lookups_use_get_open_poll_with_two_args() -> None:
    """Callback /answer / delete-guard paths must pass chat_id + message_id."""
    targets = {
        "src/app/handlers/votes.py": "call_msg_chk",
        "src/app/host_commands/membership.py": "add_answer",
        "src/domain/moderation/prevote_messages.py": "pre_return",
    }
    for rel, func_name in targets.items():
        path = REPO_ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                fn = node
                break
        assert fn is not None, f"{rel}:{func_name}"
        calls = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "get_open_poll"
        ]
        assert calls, f"{rel}:{func_name} missing get_open_poll"
        for call in calls:
            assert len(call.args) >= 2, f"{rel}:{func_name} get_open_poll needs 2 args"


def test_duplicate_and_timer_paths_use_unique_id_lookup() -> None:
    """Duplicate checks and engine completion resolve by unique_id, not message-only."""
    for rel, func_name in (
        ("src/voting/bases.py", "is_voting_exist"),
        ("src/domain/moderation/prevote_join.py", "is_voting_exist"),
        ("src/domain/admin/prevote_op.py", "is_voting_exist_op"),
        ("src/voting/engine.py", "vote_result"),
    ):
        path = REPO_ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name
        )
        names = _attr_call_names(fn)
        assert "get_poll_by_unique_id" in names, rel
        assert "get_poll" not in names, rel


def test_engine_timer_and_restart_pass_unique_id_to_vote_result() -> None:
    """vote_timer / auto_restart_polls must call vote_result(unique_id, ...)."""
    path = REPO_ROOT / "src/voting/engine.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for func_name in ("vote_timer", "auto_restart_polls"):
        fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name
        )
        result_calls = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "vote_result"
        ]
        assert result_calls, func_name
        for call in result_calls:
            assert call.args, f"{func_name} vote_result missing args"
            first = call.args[0]
            assert isinstance(first, ast.Name) and first.id == "unique_id", (
                f"{func_name} first arg must be unique_id, got {ast.dump(first)}"
            )


# ---------------------------------------------------------------------------
# Fake-repo behavioral contracts
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo() -> FakePollRepository:
    return FakePollRepository()


def test_two_chat_same_message_id_isolated_for_callback_lookup(
    fake_repo: FakePollRepository, monkeypatch: pytest.MonkeyPatch, teleboss_runtime
) -> None:
    """call_msg_chk must resolve by (chat_id, message_id), not message_id alone."""
    import teleboss.app.handlers.votes as votes_mod

    fake_repo.seed(
        _row("uid-a", _MSG_ID, _CHAT_A, poll_type="invite"),
        _row("uid-b", _MSG_ID, _CHAT_B, poll_type="ban"),
    )
    bot = MagicMock()
    monkeypatch.setattr(votes_mod, "sqlWorker", fake_repo)
    monkeypatch.setattr(votes_mod, "bot", bot)

    got_a = votes_mod.call_msg_chk(_make_callback(chat_id=_CHAT_A, message_id=_MSG_ID, data="my_vote"))
    got_b = votes_mod.call_msg_chk(_make_callback(chat_id=_CHAT_B, message_id=_MSG_ID, data="my_vote"))

    assert got_a and got_a[0][0] == "uid-a"
    assert got_b and got_b[0][0] == "uid-b"
    assert ("get_open_poll", (_CHAT_A, _MSG_ID), {}) in fake_repo.calls
    assert ("get_open_poll", (_CHAT_B, _MSG_ID), {}) in fake_repo.calls
    assert not any(name == "get_poll" for name, *_ in fake_repo.calls)
    bot.edit_message_text.assert_not_called()


def test_answer_resolves_invite_in_command_chat_only(
    fake_repo: FakePollRepository, monkeypatch: pytest.MonkeyPatch, teleboss_runtime
) -> None:
    """`/answer` must not act on a same message_id invite from another chat."""
    from teleboss.app.host_commands import HostCommands
    import teleboss.app.host_commands.membership as membership_mod

    fake_repo.seed(
        _row(
            "invite-other",
            _MSG_ID,
            _CHAT_B,
            poll_type="invite",
            data=json.dumps([111]),
        ),
        _row(
            "invite-here",
            _MSG_ID,
            _CHAT_A,
            poll_type="invite",
            data=json.dumps([222]),
        ),
    )
    bot = MagicMock()
    monkeypatch.setattr(membership_mod, "sqlWorker", fake_repo)
    monkeypatch.setattr(membership_mod, "bot", bot)
    monkeypatch.setattr(membership_mod, "bot_name_checker", lambda _m: True)
    monkeypatch.setattr(membership_mod, "command_forbidden", lambda _m: False)
    monkeypatch.setattr(membership_mod, "topic_reply_fix", lambda _m: 0)

    message = MagicMock()
    message.chat.id = _CHAT_A
    message.reply_to_message.id = _MSG_ID
    message.reply_to_message.message_id = _MSG_ID
    message.text = "/answer hello applicant"

    HostCommands.add_answer(message)

    assert ("get_open_poll", (_CHAT_A, _MSG_ID), {}) in fake_repo.calls
    assert not any(c[0] == "get_open_poll" and c[1][0] == _CHAT_B for c in fake_repo.calls)
    assert bot.send_message.call_count == 1
    assert bot.send_message.call_args[0][0] == 222
    assert "hello applicant" in bot.send_message.call_args[0][1]


@pytest.mark.parametrize(
    "status",
    [
        ApplyVoteStatus.NOT_FOUND,
        ApplyVoteStatus.NOT_OPEN,
        ApplyVoteStatus.FAILED,
        ApplyVoteStatus.BUSY,
    ],
)
def test_vote_rejected_apply_vote_does_not_update_markup(
    status: ApplyVoteStatus,
    fake_repo: FakePollRepository,
    monkeypatch: pytest.MonkeyPatch,
    teleboss_runtime,
) -> None:
    """Rejected/failed apply_vote must not call edit_message_reply_markup."""
    import teleboss.app.handlers.votes as votes_mod

    if status != ApplyVoteStatus.NOT_FOUND:
        fake_repo.seed(
            _row(
                "v1",
                _MSG_ID,
                _CHAT_A,
                buttons=_buttons("yes", "no"),
                state="open" if status != ApplyVoteStatus.NOT_OPEN else "completing",
            )
        )

    original_apply = fake_repo.apply_vote

    def _forced_apply(chat_id, message_id, mutator, **kwargs):
        if status in (ApplyVoteStatus.NOT_FOUND, ApplyVoteStatus.NOT_OPEN):
            return original_apply(chat_id, message_id, mutator, **kwargs)
        # Exercise mutator path then force non-OK without persisting markup.
        rows = [
            r
            for r in fake_repo.by_unique.values()
            if r[3] == chat_id and r[1] == message_id
        ]
        if rows and status == ApplyVoteStatus.FAILED:
            try:
                mutator(rows[0])
            except Exception:
                pass
            return ApplyVoteResult(ApplyVoteStatus.FAILED)
        return ApplyVoteResult(status)

    if status in (ApplyVoteStatus.FAILED, ApplyVoteStatus.BUSY):
        monkeypatch.setattr(fake_repo, "apply_vote", _forced_apply)

    bot = MagicMock()
    _member_ok(bot)
    engine = MagicMock()
    engine.get_abuse_timer.return_value = False
    data = SimpleNamespace(main_chat_id=_CHAT_A, vote_mode=1, path=".")

    monkeypatch.setattr(votes_mod, "sqlWorker", fake_repo)
    monkeypatch.setattr(votes_mod, "bot", bot)
    monkeypatch.setattr(votes_mod, "poll_engine", engine)
    monkeypatch.setattr(votes_mod, "data", data)

    before = {uid: row[4] for uid, row in fake_repo.by_unique.items()}
    votes_mod.vote_button(
        _make_callback(chat_id=_CHAT_A, message_id=_MSG_ID, data="vote!_yes")
    )

    bot.edit_message_reply_markup.assert_not_called()
    after = {uid: row[4] for uid, row in fake_repo.by_unique.items()}
    assert after == before
    assert not any(name == "update_poll_votes" for name, *_ in fake_repo.calls)


def test_vote_ok_updates_markup_after_persist(
    fake_repo: FakePollRepository, monkeypatch: pytest.MonkeyPatch, teleboss_runtime
) -> None:
    """Successful apply_vote may update markup only after persistence."""
    import teleboss.app.handlers.votes as votes_mod

    fake_repo.seed(
        _row("v-ok", _MSG_ID, _CHAT_A, buttons=_buttons("yes", "no"), votes_need=99)
    )
    bot = MagicMock()
    _member_ok(bot)
    engine = MagicMock()
    engine.get_abuse_timer.return_value = False
    data = SimpleNamespace(main_chat_id=_CHAT_A, vote_mode=1, path=".")

    monkeypatch.setattr(votes_mod, "sqlWorker", fake_repo)
    monkeypatch.setattr(votes_mod, "bot", bot)
    monkeypatch.setattr(votes_mod, "poll_engine", engine)
    monkeypatch.setattr(votes_mod, "data", data)

    votes_mod.vote_button(
        _make_callback(chat_id=_CHAT_A, message_id=_MSG_ID, data="vote!_yes")
    )

    assert fake_repo.by_unique["v-ok"][4] != _buttons("yes", "no")
    bot.edit_message_reply_markup.assert_called_once()
    assert any(name == "apply_vote" for name, *_ in fake_repo.calls)


def _patch_op_stack(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fake_repo: FakePollRepository,
    bot: MagicMock,
    data: SimpleNamespace,
) -> Any:
    """Patch op + votes globals used by ``call_msg_chk`` (shared lookup)."""
    import teleboss.app.handlers.op as op_mod
    import teleboss.app.handlers.votes as votes_mod

    monkeypatch.setattr(op_mod, "sqlWorker", fake_repo)
    monkeypatch.setattr(op_mod, "bot", bot)
    monkeypatch.setattr(op_mod, "data", data)
    monkeypatch.setattr(op_mod, "button_anonymous_checker", lambda *_a, **_k: False)
    # call_msg_chk resolves sqlWorker/bot from the votes module namespace.
    monkeypatch.setattr(votes_mod, "sqlWorker", fake_repo)
    monkeypatch.setattr(votes_mod, "bot", bot)
    monkeypatch.setattr(votes_mod, "data", data)
    return op_mod


def test_op_rejected_apply_vote_does_not_update_markup(
    fake_repo: FakePollRepository, monkeypatch: pytest.MonkeyPatch, teleboss_runtime
) -> None:
    """op! non-OK apply_vote leaves markup and stored buttons unchanged."""
    buttons = json.dumps(
        [
            {
                "button_type": "op!_can_delete_messages",
                "name": "delete ❌",
                "value": False,
            },
            {"button_type": "op!_close", "name": "Закрыть чек-лист", "user_id": 7},
        ]
    )
    fake_repo.seed(
        _row("op1", _MSG_ID, _CHAT_A, poll_type="op setup", buttons=buttons)
    )

    def _busy(chat_id, message_id, mutator, **kwargs):
        return ApplyVoteResult(ApplyVoteStatus.BUSY)

    bot = MagicMock()
    _member_ok(bot)
    data = SimpleNamespace(
        main_chat_id=_CHAT_A,
        ANONYMOUS_ID=1087968824,
        admin_allowed={"can_delete_messages": True},
    )
    op_mod = _patch_op_stack(monkeypatch, fake_repo=fake_repo, bot=bot, data=data)
    monkeypatch.setattr(fake_repo, "apply_vote", _busy)

    before = fake_repo.by_unique["op1"][4]
    op_mod.op_button(
        _make_callback(
            chat_id=_CHAT_A,
            message_id=_MSG_ID,
            data="op!_can_delete_messages",
            user_id=7,
        )
    )
    assert fake_repo.by_unique["op1"][4] == before
    bot.edit_message_reply_markup.assert_not_called()


def test_op_close_delegates_to_close_vote(
    monkeypatch: pytest.MonkeyPatch, teleboss_runtime
) -> None:
    """op!_close must remain delegated to close_vote."""
    close = MagicMock()
    bot = MagicMock()
    _member_ok(bot)
    poll_row = _row(
        "op-close",
        _MSG_ID,
        _CHAT_A,
        poll_type="op",
        buttons=json.dumps(
            [{"button_type": "op!_close", "name": "Закрыть", "user_id": 7}]
        ),
    )
    fake = FakePollRepository()
    fake.seed(poll_row)
    data = SimpleNamespace(main_chat_id=_CHAT_A, ANONYMOUS_ID=1087968824)
    op_mod = _patch_op_stack(monkeypatch, fake_repo=fake, bot=bot, data=data)
    monkeypatch.setattr(op_mod, "close_vote", close)

    call = _make_callback(
        chat_id=_CHAT_A, message_id=_MSG_ID, data="op!_close", user_id=7
    )
    op_mod.op_button(call)
    close.assert_called_once_with(call)
    bot.edit_message_reply_markup.assert_not_called()


def test_duplicate_check_uses_unique_id_not_message_lookup(
    fake_repo: FakePollRepository, monkeypatch: pytest.MonkeyPatch, teleboss_runtime
) -> None:
    """PreVote.is_voting_exist looks up by unique_id only."""
    import teleboss.voting.bases as bases_mod

    fake_repo.seed(_row("dup-1", _MSG_ID, _CHAT_A))
    # Same message id in another chat must not affect logical duplicate check.
    fake_repo.seed(_row("other", _MSG_ID, _CHAT_B))

    bot = MagicMock()
    monkeypatch.setattr(bases_mod, "sqlWorker", fake_repo)
    monkeypatch.setattr(bases_mod, "bot", bot)

    prevote = object.__new__(bases_mod.PreVote)
    prevote.unique_id = "dup-1"
    prevote.message = MagicMock()

    assert prevote.is_voting_exist() is True
    assert any(
        name == "get_poll_by_unique_id" and args == ("dup-1",)
        for name, args, _ in fake_repo.calls
    )
    assert not any(name == "get_poll" for name, *_ in fake_repo.calls)
    bot.reply_to.assert_called_once()


def test_expired_duplicate_cleanup_uses_rem_rec_on_unique_id(
    fake_repo: FakePollRepository, monkeypatch: pytest.MonkeyPatch, teleboss_runtime
) -> None:
    """Expired logical polls are removed via rem_rec(unique_id)."""
    import teleboss.voting.bases as bases_mod

    fake_repo.seed(_row("expired", _MSG_ID, _CHAT_A, timer=int(time.time()) - 10))
    bot = MagicMock()
    monkeypatch.setattr(bases_mod, "sqlWorker", fake_repo)
    monkeypatch.setattr(bases_mod, "bot", bot)

    prevote = object.__new__(bases_mod.PreVote)
    prevote.unique_id = "expired"
    prevote.message = MagicMock()

    assert prevote.is_voting_exist() is False
    assert "expired" not in fake_repo.by_unique
    assert ("rem_rec", ("expired",), {}) in fake_repo.calls


def test_engine_vote_result_looks_up_by_unique_id(
    fake_repo: FakePollRepository, monkeypatch: pytest.MonkeyPatch, teleboss_runtime
) -> None:
    """Timer/completion path resolves the poll via get_poll_by_unique_id."""
    import teleboss.voting.engine as engine_mod

    fake_repo.seed(_row("timer-1", _MSG_ID, _CHAT_A, state="completed"))
    monkeypatch.setattr(engine_mod, "sqlWorker", fake_repo)

    engine = engine_mod.poll_engine
    engine.vote_result("timer-1", _MSG_ID)

    assert ("get_poll_by_unique_id", ("timer-1",), {}) in fake_repo.calls
    assert not any(name == "get_poll" for name, *_ in fake_repo.calls)
