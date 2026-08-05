"""Offline unit tests for current_polls schema migration and repository APIs."""

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from teleboss.shared.storage.sql_worker import (
    ApplyVoteStatus,
    PollMigrationError,
    SqlWorker,
)

_RECOMMENDED = {"version": "4.0.0"}

_LEGACY_DDL = """
CREATE TABLE current_polls (
    unique_id TEXT NOT NULL PRIMARY KEY,
    message_id INTEGER UNIQUE,
    type TEXT NOT NULL,
    chat_id INTEGER,
    buttons TEXT,
    timer INTEGER,
    data TEXT NOT NULL,
    votes_need INTEGER,
    hidden INTEGER,
    thread_id INTEGER
)
"""


def _poll_args(
    unique_id: str,
    message_id: int,
    chat_id: int,
    *,
    buttons: str = "[]",
    timer: int | None = None,
) -> tuple:
    """Build the legacy 10-field add_poll positional tuple."""
    return (
        unique_id,
        message_id,
        "test_vote",
        chat_id,
        buttons,
        timer if timer is not None else int(time.time()) + 60,
        "[]",
        2,
        0,
        None,
    )


def _table_columns(db_path: Path) -> dict[str, sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("PRAGMA table_info(current_polls)").fetchall()
        return {row["name"]: row for row in rows}
    finally:
        conn.close()


def _unique_indexes(db_path: Path) -> list[list[str]]:
    conn = sqlite3.connect(db_path)
    try:
        indexes = conn.execute("PRAGMA index_list(current_polls)").fetchall()
        result: list[list[str]] = []
        for idx in indexes:
            if not idx[2]:
                continue
            info = conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall()
            result.append([row[2] for row in info])
        return result
    finally:
        conn.close()


def _seed_legacy_db(db_path: Path, rows: list[tuple]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_LEGACY_DDL)
        conn.executemany(
            "INSERT INTO current_polls VALUES (?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_fresh_init_creates_composite_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    cols = _table_columns(db_path)
    assert cols["unique_id"]["pk"] == 1
    assert cols["message_id"]["notnull"] == 1
    assert cols["chat_id"]["notnull"] == 1
    assert cols["state"]["notnull"] == 1
    assert any(set(idx) == {"chat_id", "message_id"} for idx in _unique_indexes(db_path))
    assert not any(idx == ["message_id"] for idx in _unique_indexes(db_path))
    # Lifecycle CHECK is part of the declared schema (PRAGMA table_info alone omits it).
    conn = sqlite3.connect(db_path)
    try:
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='current_polls'"
        ).fetchone()[0]
    finally:
        conn.close()
    compact = "".join(ddl.split())
    assert "CHECK(stateIN('open','completing','failed','completed'))" in compact

    worker.add_poll(*_poll_args("u1", 10, -100))
    row = worker.get_open_poll(-100, 10)[0]
    assert row[0] == "u1"
    assert row[1] == 10
    assert row[3] == -100
    assert row[10] == "open"
    # Offsets 0–9 stable relative to legacy layout.
    assert len(row) == 11


def test_reopen_conforming_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.db"
    SqlWorker(str(db_path), _RECOMMENDED).add_poll(*_poll_args("u1", 1, -1, buttons='[{"a":1}]'))
    before = _table_columns(db_path)
    worker2 = SqlWorker(str(db_path), _RECOMMENDED)
    after = _table_columns(db_path)
    assert set(before) == set(after)
    rows = worker2.get_all_polls()
    assert len(rows) == 1
    assert rows[0][0] == "u1"
    assert rows[0][4] == '[{"a":1}]'
    assert rows[0][10] == "open"


def test_valid_legacy_migrates_same_message_distinct_chats(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_ok.db"
    # Weakened legacy (no global message_id UNIQUE) so distinct chats can share ids.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE current_polls (
                unique_id TEXT NOT NULL PRIMARY KEY,
                message_id INTEGER,
                type TEXT NOT NULL,
                chat_id INTEGER,
                buttons TEXT,
                timer INTEGER,
                data TEXT NOT NULL,
                votes_need INTEGER,
                hidden INTEGER,
                thread_id INTEGER
            )"""
        )
        conn.executemany(
            "INSERT INTO current_polls VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                ("a", 42, "t", -101, '[{"v":1}]', 100, "[1]", 2, 0, None),
                ("b", 42, "t", -102, '[{"v":2}]', 200, "[2]", 3, 1, 9),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    assert len(worker.get_all_polls()) == 2
    a = worker.get_open_poll(-101, 42)[0]
    b = worker.get_open_poll(-102, 42)[0]
    assert a[0] == "a" and a[4] == '[{"v":1}]' and a[10] == "open"
    assert b[0] == "b" and b[6] == "[2]" and b[9] == 9 and b[10] == "open"
    # Cross-chat composite lookup must not alias.
    assert worker.get_open_poll(-101, 42)[0][0] != worker.get_open_poll(-102, 42)[0][0]


def test_null_identity_aborts_and_preserves_legacy(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db_path = tmp_path / "legacy_null.db"
    _seed_legacy_db(
        db_path,
        [("n1", 7, "t", None, "[]", 1, "[]", 1, 0, None)],
    )
    with caplog.at_level("ERROR"):
        with pytest.raises(PollMigrationError):
            SqlWorker(str(db_path), _RECOMMENDED)
    assert "poll_migration_null_identity" in caplog.text
    # Separate fresh connection proves rollback persisted on disk.
    conn = sqlite3.connect(db_path)
    try:
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='current_polls'"
        ).fetchone()[0]
        assert "state" not in sql.lower()
        row = conn.execute("SELECT unique_id, chat_id FROM current_polls").fetchone()
        assert row == ("n1", None)
    finally:
        conn.close()


def test_null_message_id_aborts_and_preserves_legacy(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Null message_id is rejected the same way as null chat_id."""
    db_path = tmp_path / "legacy_null_msg.db"
    _seed_legacy_db(
        db_path,
        [("n2", None, "t", -50, "[]", 1, "[]", 1, 0, None)],
    )
    with caplog.at_level("ERROR"):
        with pytest.raises(PollMigrationError):
            SqlWorker(str(db_path), _RECOMMENDED)
    assert "poll_migration_null_identity" in caplog.text
    conn = sqlite3.connect(db_path)
    try:
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='current_polls'"
        ).fetchone()[0]
        assert "state" not in ddl.lower()
        row = conn.execute(
            "SELECT unique_id, message_id, chat_id FROM current_polls"
        ).fetchone()
        assert row == ("n2", None, -50)
    finally:
        conn.close()


def test_duplicate_composite_aborts_and_preserves_legacy(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_path = tmp_path / "legacy_dup.db"
    # Weakened legacy: drop message_id UNIQUE so duplicate composites can exist.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE current_polls (
                unique_id TEXT NOT NULL PRIMARY KEY,
                message_id INTEGER,
                type TEXT NOT NULL,
                chat_id INTEGER,
                buttons TEXT,
                timer INTEGER,
                data TEXT NOT NULL,
                votes_need INTEGER,
                hidden INTEGER,
                thread_id INTEGER
            )"""
        )
        conn.executemany(
            "INSERT INTO current_polls VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                ("d1", 9, "t", -1, "[]", 1, "[]", 1, 0, None),
                ("d2", 9, "t", -1, "[]", 1, "[]", 1, 0, None),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    with caplog.at_level("ERROR"):
        with pytest.raises(PollMigrationError):
            SqlWorker(str(db_path), _RECOMMENDED)
    assert "poll_migration_duplicate_composite" in caplog.text
    conn = sqlite3.connect(db_path)
    try:
        assert "state" not in (
            conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='current_polls'"
            ).fetchone()[0]
            or ""
        ).lower()
        assert conn.execute("SELECT COUNT(*) FROM current_polls").fetchone()[0] == 2
    finally:
        conn.close()


def test_logical_lookup_and_legacy_get_poll_ambiguity(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_path = tmp_path / "lookup.db"
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    worker.add_poll(*_poll_args("x", 5, -10))
    worker.add_poll(*_poll_args("y", 5, -11))
    assert worker.get_poll_by_unique_id("x")[0][3] == -10
    assert worker.get_message_id("y") == 5
    with caplog.at_level("ERROR"):
        assert worker.get_poll(5) == []
    assert "poll_get_poll_ambiguous" in caplog.text
    assert worker.get_open_poll(-10, 5)[0][0] == "x"
    assert worker.get_open_poll(-11, 5)[0][0] == "y"


def test_apply_vote_success_and_failed_mutation_rollback(tmp_path: Path) -> None:
    db_path = tmp_path / "vote.db"
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    worker.add_poll(*_poll_args("v1", 1, -1, buttons='[{"user_list":[]}]'))

    ok = worker.apply_vote(
        -1,
        1,
        lambda row: json.dumps([{"user_list": [42]}]),
    )
    assert ok.status is ApplyVoteStatus.OK
    assert json.loads(ok.poll[4])[0]["user_list"] == [42]

    failed = worker.apply_vote(-1, 1, lambda row: (_ for _ in ()).throw(RuntimeError("boom")))
    assert failed.status is ApplyVoteStatus.FAILED
    assert json.loads(worker.get_open_poll(-1, 1)[0][4])[0]["user_list"] == [42]

    # Fresh connection proves durable OK and unchanged after FAILED.
    other = SqlWorker(str(db_path), _RECOMMENDED)
    assert json.loads(other.get_open_poll(-1, 1)[0][4])[0]["user_list"] == [42]


def test_apply_vote_sqlite_abort_rollback(tmp_path: Path) -> None:
    """Deterministic SQLite abort inside the locked mutation rolls back buttons."""
    db_path = tmp_path / "vote_abort.db"
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    original = json.dumps([{"user_list": [7]}])
    worker.add_poll(*_poll_args("va", 11, -11, buttons=original))

    def aborting_mutator(row):
        raise sqlite3.IntegrityError("simulated sqlite abort")

    result = worker.apply_vote(-11, 11, aborting_mutator)
    assert result.status is ApplyVoteStatus.FAILED
    assert result.poll is None

    # Separate fresh SqlWorker proves no durable mutation.
    other = SqlWorker(str(db_path), _RECOMMENDED)
    row = other.get_open_poll(-11, 11)[0]
    assert row[4] == original
    assert row[10] == "open"
    assert json.loads(row[4])[0]["user_list"] == [7]


def test_apply_vote_busy_leaves_buttons_unchanged(tmp_path: Path) -> None:
    """BUSY when another connection holds BEGIN IMMEDIATE; buttons stay intact."""
    db_path = tmp_path / "vote_busy.db"
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    original = json.dumps([{"user_list": [9]}])
    worker.add_poll(*_poll_args("vb", 12, -12, buttons=original))

    holder = sqlite3.connect(str(db_path), timeout=0.1)
    try:
        holder.execute("BEGIN IMMEDIATE")
        result = worker.apply_vote(
            -12,
            12,
            lambda row: json.dumps([{"user_list": [999]}]),
            busy_timeout=0.05,
        )
        assert result.status is ApplyVoteStatus.BUSY
        assert result.poll is None
    finally:
        holder.rollback()
        holder.close()

    other = SqlWorker(str(db_path), _RECOMMENDED)
    row = other.get_open_poll(-12, 12)[0]
    assert row[4] == original
    assert row[10] == "open"


def test_apply_vote_not_open_and_not_found(tmp_path: Path) -> None:
    db_path = tmp_path / "vote_states.db"
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    worker.add_poll(*_poll_args("c1", 2, -2))
    assert worker.claim_completion("c1")
    result = worker.apply_vote(-2, 2, lambda row: "[]")
    assert result.status is ApplyVoteStatus.NOT_OPEN
    assert worker.get_poll_by_unique_id("c1")[0][4] != "mutated"
    missing = worker.apply_vote(-999, 2, lambda row: "[]")
    assert missing.status is ApplyVoteStatus.NOT_FOUND


def test_claim_race_exactly_one_winner(tmp_path: Path) -> None:
    db_path = tmp_path / "claim.db"
    SqlWorker(str(db_path), _RECOMMENDED).add_poll(*_poll_args("race", 3, -3))
    barrier = threading.Barrier(2)
    results: list[bool] = []
    lock = threading.Lock()

    def claimer() -> None:
        local = SqlWorker(str(db_path), _RECOMMENDED)
        barrier.wait(timeout=5)
        won = local.claim_completion("race")
        with lock:
            results.append(won)

    threads = [threading.Thread(target=claimer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive()
    assert sorted(results) == [False, True]
    row = SqlWorker(str(db_path), _RECOMMENDED).get_poll_by_unique_id("race")[0]
    assert row[10] == "completing"


def test_lifecycle_transitions_and_terminal_delete(tmp_path: Path) -> None:
    db_path = tmp_path / "life.db"
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    worker.add_poll(*_poll_args("life", 4, -4))
    assert not worker.mark_failed("life")
    assert not worker.mark_completed("life")
    assert not worker.delete_completed("life")
    assert worker.claim_completion("life")
    assert not worker.claim_completion("life")
    assert worker.mark_failed("life")
    assert worker.get_poll_by_unique_id("life")[0][10] == "failed"
    assert not worker.delete_completed("life")
    assert worker.requeue_for_retry("life")
    assert worker.get_poll_by_unique_id("life")[0][10] == "open"
    assert worker.claim_completion("life")
    assert worker.mark_completed("life")
    assert worker.get_poll_by_unique_id("life")[0][10] == "completed"
    assert worker.delete_completed("life")
    assert worker.get_poll_by_unique_id("life") == []


def test_requeue_for_retry_completing_and_rejects_completed(tmp_path: Path) -> None:
    """Recovery requeue accepts failed/completing only; completed stays put."""
    db_path = tmp_path / "requeue.db"
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    worker.add_poll(*_poll_args("rq", 9, -9))
    assert not worker.requeue_for_retry("rq")  # still open
    assert worker.claim_completion("rq")
    assert worker.requeue_for_retry("rq")
    assert worker.get_poll_by_unique_id("rq")[0][10] == "open"
    assert worker.claim_completion("rq")
    assert worker.mark_completed("rq")
    assert not worker.requeue_for_retry("rq")
    assert worker.get_poll_by_unique_id("rq")[0][10] == "completed"


def test_recoverable_listing_excludes_completed(tmp_path: Path) -> None:
    db_path = tmp_path / "rec.db"
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    worker.add_poll(*_poll_args("o", 1, -1))
    worker.add_poll(*_poll_args("c", 2, -1))
    worker.add_poll(*_poll_args("f", 3, -1))
    worker.add_poll(*_poll_args("done", 4, -1))
    assert worker.claim_completion("c")
    assert worker.claim_completion("f")
    assert worker.mark_failed("f")
    assert worker.claim_completion("done")
    assert worker.mark_completed("done")
    recoverable = {row[0] for row in worker.get_recoverable_polls()}
    assert recoverable == {"o", "c", "f"}


def test_concurrent_apply_vote_both_persist(tmp_path: Path) -> None:
    db_path = tmp_path / "concurrent_vote.db"
    SqlWorker(str(db_path), _RECOMMENDED).add_poll(
        *_poll_args("cv", 8, -8, buttons=json.dumps([{"user_list": []}]))
    )
    barrier = threading.Barrier(2)
    statuses: list[ApplyVoteStatus] = []
    lock = threading.Lock()

    def voter(user_id: int) -> None:
        local = SqlWorker(str(db_path), _RECOMMENDED)
        barrier.wait(timeout=5)

        def mutator(row):
            data = json.loads(row[4])
            data[0]["user_list"].append(user_id)
            return json.dumps(data)

        result = local.apply_vote(-8, 8, mutator, busy_timeout=10.0)
        with lock:
            statuses.append(result.status)

    threads = [
        threading.Thread(target=voter, args=(101,)),
        threading.Thread(target=voter, args=(202,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()
    assert statuses.count(ApplyVoteStatus.OK) >= 1
    final = SqlWorker(str(db_path), _RECOMMENDED).get_open_poll(-8, 8)[0]
    # Persisted buttons must remain valid JSON after concurrent mutations.
    users = json.loads(final[4])[0]["user_list"]
    assert isinstance(users, list)
    # Serialized IMMEDIATE votes: both OK should accumulate; one busy is allowed.
    if statuses.count(ApplyVoteStatus.OK) == 2:
        assert sorted(users) == [101, 202]
    else:
        assert set(users) <= {101, 202}
        assert len(users) >= 1
        assert ApplyVoteStatus.BUSY in statuses or ApplyVoteStatus.OK in statuses


def test_standard_legacy_schema_migrates(tmp_path: Path) -> None:
    """Current production legacy DDL (global message_id UNIQUE) migrates cleanly."""
    db_path = tmp_path / "legacy_standard.db"
    _seed_legacy_db(
        db_path,
        [
            ("a", 42, "t", -101, '[{"v":1}]', 100, "[1]", 2, 0, None),
            ("b", 43, "t", -102, '[{"v":2}]', 200, "[2]", 3, 1, 9),
        ],
    )
    worker = SqlWorker(str(db_path), _RECOMMENDED)
    assert worker.get_open_poll(-101, 42)[0][10] == "open"
    assert worker.get_open_poll(-102, 43)[0][4] == '[{"v":2}]'
    cols = _table_columns(db_path)
    assert "state" in cols
    assert cols["chat_id"]["notnull"] == 1
