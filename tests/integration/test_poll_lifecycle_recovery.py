"""Integration tests for poll claim, recovery, serialization, and cleanup."""

from __future__ import annotations

import threading
import time
import weakref
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_RECOMMENDED = {"version": "4.0.0"}
_VOTE_TYPE = "lifecycle_test_vote"


def _poll_args(
    unique_id: str,
    message_id: int,
    chat_id: int,
    *,
    vote_type: str = _VOTE_TYPE,
    buttons: str = "[]",
    timer: int | None = None,
    data: str = "[]",
) -> tuple:
    """Build the legacy 10-field add_poll positional tuple."""
    return (
        unique_id,
        message_id,
        vote_type,
        chat_id,
        buttons,
        timer if timer is not None else int(time.time()) + 60,
        data,
        2,
        0,
        None,
    )


def _state(worker, unique_id: str) -> str | None:
    rows = worker.get_poll_by_unique_id(unique_id)
    return None if not rows else rows[0][10]


@pytest.fixture
def lifecycle_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, teleboss_runtime):
    """Function-scoped file-backed DB with engine/bootstrap worker + bot patched.

    Product imports are deferred until after ``teleboss_runtime`` seeds argv.
    """
    from teleboss.shared.storage.sql_worker import SqlWorker
    from teleboss.voting.engine import PollEngine
    import teleboss.shared.bootstrap as bootstrap_mod
    import teleboss.voting.bases as bases_mod
    import teleboss.voting.engine as engine_mod

    db_path = tmp_path / "lifecycle.db"
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    fake_bot = MagicMock()

    monkeypatch.setattr(engine_mod, "sqlWorker", worker)
    monkeypatch.setattr(bootstrap_mod, "sqlWorker", worker)
    monkeypatch.setattr(engine_mod, "bot", fake_bot)
    monkeypatch.setattr(bases_mod, "bot", fake_bot)

    saved_handlers = dict(PollEngine.post_vote_list)
    PollEngine.post_vote_list.clear()
    PollEngine._handler_locks = weakref.WeakKeyDictionary()

    yield {
        "db_path": db_path,
        "worker": worker,
        "bot": fake_bot,
        "engine_mod": engine_mod,
        "bootstrap_mod": bootstrap_mod,
        "PollEngine": PollEngine,
        # Prefer the module singleton; extra instances via object.__new__ (no ctor site).
        "poll_engine": engine_mod.poll_engine,
    }

    PollEngine.post_vote_list.clear()
    PollEngine.post_vote_list.update(saved_handlers)
    PollEngine._handler_locks = weakref.WeakKeyDictionary()


class SuccessHandler:
    """Fake post-vote that records calls and returns success."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.lock = threading.Lock()

    def post_vote(self, records) -> bool:
        with self.lock:
            self.calls.append(records)
        return True


class FalseHandler:
    """Controlled failure via explicit ``False``."""

    def post_vote(self, records) -> bool:
        return False


class RaisingHandler:
    """Unhandled exception from the handler body."""

    def post_vote(self, records) -> bool:
        raise RuntimeError("handler boom")


class LegacyNoneHandler:
    """Legacy override returning ``None`` (success absent exception)."""

    def post_vote(self, records) -> None:
        return None


class SharedSerialHandler:
    """Shared mutable handler that tracks concurrent ``post_vote`` entry."""

    def __init__(self, hold_s: float = 0.2) -> None:
        self.hold_s = hold_s
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self._mu = threading.Lock()

    def post_vote(self, records) -> bool:
        with self._mu:
            self.active += 1
            self.calls += 1
            if self.active > self.max_active:
                self.max_active = self.active
        time.sleep(self.hold_s)
        with self._mu:
            self.active -= 1
        return True


def _fresh_engine(lifecycle_db):
    """Build a distinct engine instance without a product construction-site call."""
    return object.__new__(lifecycle_db["PollEngine"])


def test_claim_race_loser_skips_handler(lifecycle_db) -> None:
    """Exactly one of two contenders claims; the loser performs no handler work."""
    PollEngine = lifecycle_db["PollEngine"]
    worker = lifecycle_db["worker"]
    handler = SuccessHandler()
    PollEngine.post_vote_list[_VOTE_TYPE] = handler
    worker.add_poll(*_poll_args("race", 1, -1))

    barrier = threading.Barrier(2)
    engines = [_fresh_engine(lifecycle_db), _fresh_engine(lifecycle_db)]

    def contender(engine) -> None:
        barrier.wait(timeout=5)
        engine.vote_result("race", 1)

    threads = [threading.Thread(target=contender, args=(eng,)) for eng in engines]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive()

    assert len(handler.calls) == 1
    assert worker.get_poll_by_unique_id("race") == []


def test_hot_path_live_completing_claim_lost_no_requeue(lifecycle_db) -> None:
    """Live ``completing`` on the hot path is claim-lost: no requeue, no handler."""
    PollEngine = lifecycle_db["PollEngine"]
    worker = lifecycle_db["worker"]
    engine = lifecycle_db["poll_engine"]
    handler = SuccessHandler()
    PollEngine.post_vote_list[_VOTE_TYPE] = handler
    worker.add_poll(*_poll_args("live-comp", 70, -70))
    assert worker.claim_completion("live-comp")
    assert _state(worker, "live-comp") == "completing"

    requeue_calls: list[str] = []
    real_requeue = worker.requeue_for_retry

    def tracking_requeue(uid: str) -> bool:
        requeue_calls.append(uid)
        return real_requeue(uid)

    worker.requeue_for_retry = tracking_requeue  # type: ignore[method-assign]

    engine.vote_result("live-comp", 70)

    assert requeue_calls == []
    assert handler.calls == []
    assert _state(worker, "live-comp") == "completing"


def test_hot_path_failed_requeues_then_completes(lifecycle_db) -> None:
    """Hot-path ``failed`` requeues to ``open``, then claims and completes."""
    PollEngine = lifecycle_db["PollEngine"]
    worker = lifecycle_db["worker"]
    engine = lifecycle_db["poll_engine"]
    handler = SuccessHandler()
    PollEngine.post_vote_list[_VOTE_TYPE] = handler
    worker.add_poll(*_poll_args("hot-fail", 71, -71))
    assert worker.claim_completion("hot-fail")
    assert worker.mark_failed("hot-fail")
    assert _state(worker, "hot-fail") == "failed"

    engine.vote_result("hot-fail", 71)

    assert len(handler.calls) == 1
    assert worker.get_poll_by_unique_id("hot-fail") == []


def test_success_path_claim_handler_complete_delete(lifecycle_db) -> None:
    """Success follows claim → handler → mark_completed → guarded delete."""
    PollEngine = lifecycle_db["PollEngine"]
    worker = lifecycle_db["worker"]
    engine = lifecycle_db["poll_engine"]
    order: list[str] = []
    real_claim = worker.claim_completion
    real_mark = worker.mark_completed
    real_delete = worker.delete_completed

    def claim(uid: str) -> bool:
        order.append("claim")
        return real_claim(uid)

    def mark(uid: str) -> bool:
        order.append("mark_completed")
        assert _state(worker, uid) == "completing"
        return real_mark(uid)

    def delete(uid: str) -> bool:
        order.append("delete_completed")
        assert _state(worker, uid) == "completed"
        return real_delete(uid)

    worker.claim_completion = claim  # type: ignore[method-assign]
    worker.mark_completed = mark  # type: ignore[method-assign]
    worker.delete_completed = delete  # type: ignore[method-assign]

    handler = SuccessHandler()
    PollEngine.post_vote_list[_VOTE_TYPE] = handler
    worker.add_poll(*_poll_args("ok", 2, -2))

    engine.vote_result("ok", 2)

    assert handler.calls and handler.calls[0][0] == "ok"
    assert order == ["claim", "mark_completed", "delete_completed"]
    assert worker.get_poll_by_unique_id("ok") == []


@pytest.mark.parametrize(
    "handler_kind",
    ["false", "raising", "missing"],
)
def test_failure_paths_mark_failed_and_retain(lifecycle_db, handler_kind: str) -> None:
    """Controlled False, raised error, and missing handler → failed + retain."""
    PollEngine = lifecycle_db["PollEngine"]
    worker = lifecycle_db["worker"]
    engine = lifecycle_db["poll_engine"]
    PollEngine.post_vote_list.pop(_VOTE_TYPE, None)
    if handler_kind == "false":
        PollEngine.post_vote_list[_VOTE_TYPE] = FalseHandler()
    elif handler_kind == "raising":
        PollEngine.post_vote_list[_VOTE_TYPE] = RaisingHandler()

    uid = f"fail-{handler_kind}"
    mid = {"false": 10, "raising": 11, "missing": 12}[handler_kind]
    worker.add_poll(*_poll_args(uid, mid, -10))
    engine.vote_result(uid, mid)

    assert _state(worker, uid) == "failed"
    assert worker.get_poll_by_unique_id(uid)


def test_base_postvote_controlled_false_and_legacy_none(lifecycle_db) -> None:
    """Base controlled failure returns False; legacy ``None`` is success."""
    from teleboss.voting.bases import PostVote
    from teleboss.voting.exceptions import InternalBotException, SilentException

    PollEngine = lifecycle_db["PollEngine"]
    worker = lifecycle_db["worker"]
    engine = lifecycle_db["poll_engine"]
    bases_bot = lifecycle_db["bot"]

    class ControlledFailPostVote(PostVote):
        _description = "controlled fail"

        def decline(self) -> None:
            raise InternalBotException("controlled")

    class SilentSuccessPostVote(PostVote):
        _description = "silent success"

        def decline(self) -> None:
            raise SilentException()

    PollEngine.post_vote_list["ctrl"] = ControlledFailPostVote()
    worker.add_poll(*_poll_args("ctrl", 20, -20, vote_type="ctrl"))
    engine.vote_result("ctrl", 20)
    assert _state(worker, "ctrl") == "failed"
    bases_bot.unpin_chat_message.assert_called()

    PollEngine.post_vote_list["legacy"] = LegacyNoneHandler()
    worker.add_poll(*_poll_args("legacy", 21, -21, vote_type="legacy"))
    engine.vote_result("legacy", 21)
    assert worker.get_poll_by_unique_id("legacy") == []

    PollEngine.post_vote_list["silent"] = SilentSuccessPostVote()
    worker.add_poll(*_poll_args("silent", 22, -22, vote_type="silent"))
    engine.vote_result("silent", 22)
    assert worker.get_poll_by_unique_id("silent") == []


def test_shared_handler_serialized_across_engines(lifecycle_db) -> None:
    """Two engines + one shared handler instance: max concurrent entry is 1."""
    PollEngine = lifecycle_db["PollEngine"]
    worker = lifecycle_db["worker"]
    shared = SharedSerialHandler(hold_s=0.25)
    PollEngine.post_vote_list[_VOTE_TYPE] = shared
    worker.add_poll(*_poll_args("s1", 31, -31))
    worker.add_poll(*_poll_args("s2", 32, -32))

    barrier = threading.Barrier(2)
    e1, e2 = _fresh_engine(lifecycle_db), _fresh_engine(lifecycle_db)
    assert e1 is not e2

    def run(engine, uid: str, mid: int) -> None:
        barrier.wait(timeout=5)
        engine.vote_result(uid, mid)

    threads = [
        threading.Thread(target=run, args=(e1, "s1", 31)),
        threading.Thread(target=run, args=(e2, "s2", 32)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive()

    assert shared.calls == 2
    assert shared.max_active == 1
    assert worker.get_poll_by_unique_id("s1") == []
    assert worker.get_poll_by_unique_id("s2") == []


def test_restart_recovery_surrogate(lifecycle_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reopen DB: future open reschedules; expired/failed/completing retry; completed excluded."""
    from teleboss.shared.storage.sql_worker import SqlWorker

    PollEngine = lifecycle_db["PollEngine"]
    db_path = lifecycle_db["db_path"]
    worker = lifecycle_db["worker"]
    engine_mod = lifecycle_db["engine_mod"]
    engine = lifecycle_db["poll_engine"]
    now = 1_700_000_000

    handler = SuccessHandler()
    PollEngine.post_vote_list[_VOTE_TYPE] = handler

    worker.add_poll(*_poll_args("future", 41, -41, timer=now + 120))
    worker.add_poll(*_poll_args("expired", 42, -42, timer=now - 10))
    worker.add_poll(*_poll_args("failed_row", 43, -43, timer=now - 10))
    worker.add_poll(*_poll_args("stranded", 44, -44, timer=now - 10))
    worker.add_poll(*_poll_args("done", 45, -45, timer=now - 10))

    assert worker.claim_completion("failed_row")
    assert worker.mark_failed("failed_row")
    assert worker.claim_completion("stranded")
    assert worker.claim_completion("done")
    assert worker.mark_completed("done")

    # Restart surrogate: new SqlWorker on the same file, rebound on engine.
    restarted = SqlWorker(str(db_path), _RECOMMENDED)
    monkeypatch.setattr(engine_mod, "sqlWorker", restarted)

    scheduled: list[tuple] = []

    class CapturingThread:
        def __init__(self, *args, **kwargs) -> None:
            self._target = kwargs.get("target")
            self._args = kwargs.get("args") or ()
            scheduled.append((self._target, self._args))

        def start(self) -> None:
            return None

    monkeypatch.setattr(engine_mod.time, "time", lambda: float(now))
    monkeypatch.setattr(engine_mod.threading, "Thread", CapturingThread)

    engine.auto_restart_polls()

    assert len(scheduled) == 1
    target, args = scheduled[0]
    assert target == engine.vote_timer
    assert args[0] == 120
    assert args[1] == "future"
    assert args[2] == 41

    assert restarted.get_poll_by_unique_id("expired") == []
    assert restarted.get_poll_by_unique_id("failed_row") == []
    assert restarted.get_poll_by_unique_id("stranded") == []
    assert _state(restarted, "done") == "completed"
    assert _state(restarted, "future") == "open"
    assert len(handler.calls) == 3


def test_auto_clear_only_deletes_completed(lifecycle_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """One cleanup sweep removes only aged completed rows; incomplete states stay."""
    worker = lifecycle_db["worker"]
    bootstrap_mod = lifecycle_db["bootstrap_mod"]
    now = 1_700_000_000
    old = now - 700

    worker.add_poll(*_poll_args("open_old", 51, -51, timer=old))
    worker.add_poll(*_poll_args("comp_old", 52, -52, timer=old))
    worker.add_poll(*_poll_args("fail_old", 53, -53, timer=old))
    worker.add_poll(*_poll_args("done_old", 54, -54, timer=old))
    worker.add_poll(*_poll_args("done_fresh", 55, -55, timer=now + 60))

    assert worker.claim_completion("comp_old")
    assert worker.claim_completion("fail_old")
    assert worker.mark_failed("fail_old")
    assert worker.claim_completion("done_old")
    assert worker.mark_completed("done_old")
    assert worker.claim_completion("done_fresh")
    assert worker.mark_completed("done_fresh")

    monkeypatch.setattr(bootstrap_mod.time, "time", lambda: float(now))

    def stop_after_one(_seconds: float) -> None:
        raise StopIteration

    monkeypatch.setattr(bootstrap_mod.time, "sleep", stop_after_one)

    with pytest.raises(StopIteration):
        bootstrap_mod.auto_clear()

    assert _state(worker, "open_old") == "open"
    assert _state(worker, "comp_old") == "completing"
    assert _state(worker, "fail_old") == "failed"
    assert worker.get_poll_by_unique_id("done_old") == []
    assert _state(worker, "done_fresh") == "completed"


def test_message_id_mismatch_skips_work(lifecycle_db) -> None:
    """Wrong message_vote_id identity check performs no claim/handler work."""
    PollEngine = lifecycle_db["PollEngine"]
    worker = lifecycle_db["worker"]
    engine = lifecycle_db["poll_engine"]
    handler = SuccessHandler()
    PollEngine.post_vote_list[_VOTE_TYPE] = handler
    worker.add_poll(*_poll_args("mm", 99, -99))
    engine.vote_result("mm", 100)
    assert _state(worker, "mm") == "open"
    assert handler.calls == []


def test_completed_row_not_replayed(lifecycle_db) -> None:
    """``vote_result`` on a durable completed row is a no-op."""
    PollEngine = lifecycle_db["PollEngine"]
    worker = lifecycle_db["worker"]
    engine = lifecycle_db["poll_engine"]
    handler = SuccessHandler()
    PollEngine.post_vote_list[_VOTE_TYPE] = handler
    worker.add_poll(*_poll_args("done2", 60, -60))
    assert worker.claim_completion("done2")
    assert worker.mark_completed("done2")
    engine.vote_result("done2", 60)
    assert handler.calls == []
    assert _state(worker, "done2") == "completed"
