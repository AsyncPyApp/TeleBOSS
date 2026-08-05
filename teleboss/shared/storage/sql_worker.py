"""SQLite storage worker for TeleBOSS polls and host tables.

``current_polls`` uses ``unique_id`` as the logical primary key and
``(chat_id, message_id)`` as the displayed-poll identity. Lifecycle state is
stored in ``state`` (offset 10). Tuple offsets 0–9 remain stable for legacy
callers.
"""

import json
import logging
import sqlite3
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Final

# Stable SELECT projection: offsets 0–9 match the historical row layout; 10 is state.
_POLL_COLUMNS: Final = (
    "unique_id, message_id, type, chat_id, buttons, timer, data, "
    "votes_need, hidden, thread_id, state"
)

_RECOVERABLE_STATES: Final = frozenset({"open", "completing", "failed"})

_CURRENT_POLLS_DDL: Final = """
CREATE TABLE current_polls (
    unique_id TEXT NOT NULL PRIMARY KEY,
    message_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    buttons TEXT,
    timer INTEGER,
    data TEXT NOT NULL,
    votes_need INTEGER,
    hidden INTEGER,
    thread_id INTEGER,
    state TEXT NOT NULL DEFAULT 'open'
        CHECK(state IN ('open', 'completing', 'failed', 'completed')),
    UNIQUE (chat_id, message_id)
)
"""

# Migration / ambiguity log categories (safe IDs only — never payloads).
_LOG_NULL_IDENTITY: Final = "poll_migration_null_identity"
_LOG_DUPLICATE_COMPOSITE: Final = "poll_migration_duplicate_composite"
_LOG_MIGRATION_FAILED: Final = "poll_migration_failed"
_LOG_GET_POLL_AMBIGUOUS: Final = "poll_get_poll_ambiguous"

PollRow = tuple  # (unique_id, message_id, type, chat_id, buttons, timer, data, votes_need, hidden, thread_id, state)
VoteMutator = Callable[[PollRow], str]


class PollMigrationError(Exception):
    """Raised when ``current_polls`` cannot be migrated without data loss risk."""


class ApplyVoteStatus(StrEnum):
    """Outcome of :meth:`SqlWorker.apply_vote` (no Telegram I/O while locked)."""

    OK = "ok"
    NOT_FOUND = "not_found"
    NOT_OPEN = "not_open"
    BUSY = "busy"
    FAILED = "failed"


class ApplyVoteResult:
    """Bounded result for an atomic vote mutation attempt.

    Attributes:
        status: Outcome category; non-``OK`` means no durable mutation.
        poll: Updated poll row on ``OK``; otherwise ``None``.
    """

    __slots__ = ("status", "poll")

    def __init__(self, status: ApplyVoteStatus, poll: PollRow | None = None) -> None:
        """Bind status and optional updated row.

        Args:
            status: Mutation outcome.
            poll: Persisted row after a successful mutation.
        """
        self.status = status
        self.poll = poll


class SQLWrapper:
    """Context manager that opens a SQLite connection and commits on success."""

    def __init__(self, dbname: str) -> None:
        """Store the database path.

        Args:
            dbname: Path to the SQLite database file.
        """
        self.dbname = dbname

    def __enter__(self) -> SQLWrapper:
        """Open the connection and cursor.

        Returns:
            This wrapper with ``cursor`` ready for use.
        """
        self.sqlite_connection = sqlite3.connect(self.dbname)
        self.cursor = self.sqlite_connection.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit when no exception occurred, then close resources."""
        if not exc_type:
            self.sqlite_connection.commit()
        self.cursor.close()
        self.sqlite_connection.close()


class SqlWorker:
    """Host SQLite facade including the poll repository contract (T01)."""

    dbname = ""

    def __init__(self, dbname: str, recommended) -> None:
        """Open or create the database and ensure ``current_polls`` schema.

        Args:
            dbname: Path to the SQLite database file.
            recommended: Default JSON-serializable params seed when empty.
        """
        self.dbname = dbname

        sqlite_connection = sqlite3.connect(dbname)
        cursor = sqlite_connection.cursor()
        try:
            self._ensure_current_polls_schema(sqlite_connection, cursor)
            cursor.execute("""CREATE TABLE if not exists abuse (
                                        user_id INTEGER PRIMARY KEY,
                                        start_time INTEGER,
                                        timer INTEGER);""")
            cursor.execute("""CREATE TABLE if not exists whitelist (
                                        user_id INTEGER PRIMARY KEY);""")
            cursor.execute("""CREATE TABLE if not exists mailing (
                                        user_id INTEGER PRIMARY KEY);""")
            cursor.execute("""CREATE TABLE if not exists rating (
                                        user_id INTEGER PRIMARY KEY,
                                        rate INTEGER);""")
            cursor.execute("""CREATE TABLE if not exists abuse_random (
                                        chat_id INTEGER PRIMARY KEY,
                                        abuse_random INTEGER);""")
            cursor.execute("""CREATE TABLE if not exists allies (
                                        chat_id INTEGER PRIMARY KEY);""")
            cursor.execute("""CREATE TABLE if not exists params (
                                        params TEXT PRIMARY KEY);""")
            cursor.execute("""CREATE TABLE if not exists captcha (
                                        message_id TEXT,
                                        user_id TEXT,
                                        max_value INTEGER,
                                        username TEXT);""")
            cursor.execute("""CREATE TABLE if not exists marmalade (
                                        user_id INTEGER PRIMARY KEY,
                                        entry_time INTEGER);""")
            cursor.execute("""DELETE FROM captcha""")
            cursor.execute("""SELECT * FROM params""")
            records = cursor.fetchall()
            if not records:
                cursor.execute("""INSERT INTO params VALUES (?)""", (json.dumps(recommended),))

            sqlite_connection.commit()
        except Exception:
            sqlite_connection.rollback()
            raise
        finally:
            cursor.close()
            sqlite_connection.close()

    # --- Schema / migration -------------------------------------------------

    def _ensure_current_polls_schema(
        self, conn: sqlite3.Connection, cursor: sqlite3.Cursor
    ) -> None:
        """Create or migrate ``current_polls`` to the composite identity schema.

        A conforming schema is a no-op. Legacy/nonconforming tables are rebuilt
        inside one ``BEGIN IMMEDIATE`` transaction after row validation.

        Args:
            conn: Open SQLite connection.
            cursor: Cursor bound to ``conn``.

        Raises:
            PollMigrationError: When rows cannot be mapped safely; original
                schema and data are left unchanged.
        """
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='current_polls'"
        )
        exists = cursor.fetchone() is not None
        if not exists:
            cursor.execute(_CURRENT_POLLS_DDL)
            return
        if self._is_current_polls_conforming(cursor):
            return
        self._migrate_current_polls(conn, cursor)

    def _is_current_polls_conforming(self, cursor: sqlite3.Cursor) -> bool:
        """Return whether ``current_polls`` already matches the target schema.

        Args:
            cursor: Cursor on the target database.

        Returns:
            True when columns, NOT NULL identity, composite unique, and state
            constraints are present and message_id is not globally unique alone.
        """
        cursor.execute("PRAGMA table_info(current_polls)")
        cols = {row[1]: row for row in cursor.fetchall()}
        required = (
            "unique_id",
            "message_id",
            "type",
            "chat_id",
            "buttons",
            "timer",
            "data",
            "votes_need",
            "hidden",
            "thread_id",
            "state",
        )
        if any(name not in cols for name in required):
            return False
        if cols["unique_id"][5] != 1:  # pk
            return False
        if cols["message_id"][3] != 1 or cols["chat_id"][3] != 1:  # notnull
            return False
        if cols["state"][3] != 1:
            return False

        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='current_polls'"
        )
        create_sql = (cursor.fetchone() or (None,))[0] or ""
        compact = "".join(create_sql.upper().split())
        if "CHECK" not in compact or "OPEN" not in compact:
            return False

        has_composite_unique = False
        has_message_only_unique = False
        cursor.execute("PRAGMA index_list(current_polls)")
        for idx in cursor.fetchall():
            # (seq, name, unique, origin, partial)
            if not idx[2]:
                continue
            idx_name = idx[1].replace("'", "''")
            cursor.execute(f"PRAGMA index_info('{idx_name}')")
            col_names = [info[2] for info in cursor.fetchall()]
            if set(col_names) == {"chat_id", "message_id"} and len(col_names) == 2:
                has_composite_unique = True
            if col_names == ["message_id"]:
                has_message_only_unique = True

        if has_message_only_unique:
            return False
        if has_composite_unique:
            return True
        return "UNIQUE(CHAT_ID,MESSAGE_ID)" in compact

    def _migrate_current_polls(
        self, conn: sqlite3.Connection, cursor: sqlite3.Cursor
    ) -> None:
        """Validate legacy rows and rebuild ``current_polls`` transactionally.

        Args:
            conn: Open SQLite connection.
            cursor: Cursor bound to ``conn``.

        Raises:
            PollMigrationError: On null/duplicate identity or any migration error.
        """
        # End any deferred transaction started by PRAGMA/SELECT before IMMEDIATE.
        conn.commit()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                "SELECT unique_id, message_id, type, chat_id, buttons, timer, data, "
                "votes_need, hidden, thread_id FROM current_polls"
            )
            rows = cursor.fetchall()
            self._validate_legacy_poll_rows(rows)

            cursor.execute("DROP TABLE IF EXISTS current_polls_migrating")
            cursor.execute(
                _CURRENT_POLLS_DDL.replace(
                    "CREATE TABLE current_polls",
                    "CREATE TABLE current_polls_migrating",
                    1,
                )
            )
            cursor.executemany(
                """INSERT INTO current_polls_migrating (
                    unique_id, message_id, type, chat_id, buttons, timer, data,
                    votes_need, hidden, thread_id, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
                rows,
            )
            cursor.execute("DROP TABLE current_polls")
            cursor.execute(
                "ALTER TABLE current_polls_migrating RENAME TO current_polls"
            )
            conn.commit()
        except PollMigrationError:
            conn.rollback()
            raise
        except Exception as exc:
            conn.rollback()
            logging.error(
                "%s category=%s error_type=%s",
                "current_polls migration aborted",
                _LOG_MIGRATION_FAILED,
                type(exc).__name__,
            )
            raise PollMigrationError(
                "current_polls migration failed; legacy schema left unchanged"
            ) from exc

    def _validate_legacy_poll_rows(self, rows: list[tuple]) -> None:
        """Reject null or duplicate composite identities before destructive DDL.

        Args:
            rows: Legacy poll tuples (offsets 0–9).

        Raises:
            PollMigrationError: When any row is unsafe to migrate.
        """
        seen: dict[tuple[int, int], str] = {}
        for row in rows:
            unique_id = row[0]
            message_id = row[1]
            chat_id = row[3]
            if chat_id is None or message_id is None:
                logging.error(
                    "%s category=%s unique_id=%s chat_id=%s message_id=%s",
                    "current_polls migration rejected",
                    _LOG_NULL_IDENTITY,
                    unique_id,
                    chat_id,
                    message_id,
                )
                raise PollMigrationError(
                    f"null poll identity unique_id={unique_id!r} "
                    f"chat_id={chat_id!r} message_id={message_id!r}"
                )
            key = (int(chat_id), int(message_id))
            prior = seen.get(key)
            if prior is not None:
                logging.error(
                    "%s category=%s chat_id=%s message_id=%s "
                    "unique_id=%s conflicting_unique_id=%s",
                    "current_polls migration rejected",
                    _LOG_DUPLICATE_COMPOSITE,
                    key[0],
                    key[1],
                    prior,
                    unique_id,
                )
                raise PollMigrationError(
                    f"duplicate composite identity chat_id={key[0]} "
                    f"message_id={key[1]} unique_ids={prior!r},{unique_id!r}"
                )
            seen[key] = str(unique_id)

    # --- Poll repository (lifecycle-aware) ----------------------------------

    def _fetch_polls(
        self, cursor: sqlite3.Cursor, where: str, params: tuple
    ) -> list[PollRow]:
        """Run a projected poll SELECT.

        Args:
            cursor: Active cursor.
            where: SQL WHERE clause without the leading keyword, or empty.
            params: Bound parameters.

        Returns:
            Matching poll rows with stable column order.
        """
        sql = f"SELECT {_POLL_COLUMNS} FROM current_polls"
        if where:
            sql = f"{sql} WHERE {where}"
        cursor.execute(sql, params)
        return cursor.fetchall()

    def get_open_poll(self, chat_id: int, message_id: int) -> list[PollRow]:
        """Look up a displayed open poll by composite identity.

        Args:
            chat_id: Telegram chat id.
            message_id: Telegram message id within that chat.

        Returns:
            Zero or one open poll row; never cross-resolves other chats.
        """
        with SQLWrapper(self.dbname) as sql_wrapper:
            return self._fetch_polls(
                sql_wrapper.cursor,
                "chat_id = ? AND message_id = ? AND state = 'open'",
                (chat_id, message_id),
            )

    def get_poll_by_unique_id(self, unique_id: str) -> list[PollRow]:
        """Look up a poll by logical ``unique_id`` (timer/recovery).

        Args:
            unique_id: Logical poll primary key.

        Returns:
            Zero or one poll row in any lifecycle state.
        """
        with SQLWrapper(self.dbname) as sql_wrapper:
            return self._fetch_polls(
                sql_wrapper.cursor, "unique_id = ?", (unique_id,)
            )

    def get_recoverable_polls(self) -> list[PollRow]:
        """List polls that restart recovery may retry.

        Returns:
            Rows in ``open``, ``completing``, or ``failed`` state.
        """
        with SQLWrapper(self.dbname) as sql_wrapper:
            placeholders = ",".join("?" * len(_RECOVERABLE_STATES))
            return self._fetch_polls(
                sql_wrapper.cursor,
                f"state IN ({placeholders})",
                tuple(sorted(_RECOVERABLE_STATES)),
            )

    def apply_vote(
        self,
        chat_id: int,
        message_id: int,
        mutator: VoteMutator,
        *,
        busy_timeout: float = 5.0,
    ) -> ApplyVoteResult:
        """Atomically mutate buttons for an open composite poll.

        Owns ``BEGIN IMMEDIATE → open lookup → local mutator → persist → commit``.
        Does not perform Telegram or network I/O while holding the write lock.

        Args:
            chat_id: Telegram chat id.
            message_id: Telegram message id within that chat.
            mutator: Pure callback receiving the open poll row and returning the
                new buttons JSON string. Must not perform I/O.
            busy_timeout: SQLite busy timeout in seconds before ``BUSY``.

        Returns:
            :class:`ApplyVoteResult` with a defined no-mutation outcome on
            not-found, not-open, busy, or failure.
        """
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(self.dbname, timeout=busy_timeout)
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                return ApplyVoteResult(ApplyVoteStatus.BUSY)

            rows = self._fetch_polls(
                cursor,
                "chat_id = ? AND message_id = ?",
                (chat_id, message_id),
            )
            if not rows:
                conn.rollback()
                return ApplyVoteResult(ApplyVoteStatus.NOT_FOUND)
            poll = rows[0]
            if poll[10] != "open":
                conn.rollback()
                return ApplyVoteResult(ApplyVoteStatus.NOT_OPEN)

            try:
                new_buttons = mutator(poll)
                if not isinstance(new_buttons, str):
                    raise TypeError("vote mutator must return a buttons JSON str")
                cursor.execute(
                    "UPDATE current_polls SET buttons = ? "
                    "WHERE unique_id = ? AND state = 'open'",
                    (new_buttons, poll[0]),
                )
                if cursor.rowcount != 1:
                    conn.rollback()
                    return ApplyVoteResult(ApplyVoteStatus.NOT_OPEN)
                updated = self._fetch_polls(
                    cursor, "unique_id = ?", (poll[0],)
                )
                conn.commit()
                return ApplyVoteResult(
                    ApplyVoteStatus.OK, updated[0] if updated else None
                )
            except sqlite3.OperationalError:
                conn.rollback()
                return ApplyVoteResult(ApplyVoteStatus.BUSY)
            except Exception:
                conn.rollback()
                return ApplyVoteResult(ApplyVoteStatus.FAILED)
        except sqlite3.OperationalError:
            if conn is not None:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            return ApplyVoteResult(ApplyVoteStatus.BUSY)
        except Exception:
            if conn is not None:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            return ApplyVoteResult(ApplyVoteStatus.FAILED)
        finally:
            if conn is not None:
                conn.close()

    def claim_completion(self, unique_id: str) -> bool:
        """Conditionally claim an open poll for completion (``open`` → ``completing``).

        Args:
            unique_id: Logical poll primary key.

        Returns:
            True when this caller won the claim; False otherwise.
        """
        return self._conditional_state_update(
            unique_id, from_state="open", to_state="completing"
        )

    def requeue_for_retry(self, unique_id: str) -> bool:
        """Requeue a stranded ``completing`` or ``failed`` poll to ``open``.

        Recovery path that makes a non-open incomplete row claimable again.
        Callers should requeue ``completing`` only from restart recovery
        (not from live timer/close/threshold contenders). Does not touch
        ``completed`` rows. ``claim_completion`` remains the only
        ``open`` → ``completing`` gate.

        Args:
            unique_id: Logical poll primary key.

        Returns:
            True when the row was updated to ``open``.
        """
        conn = sqlite3.connect(self.dbname, timeout=5.0)
        try:
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                return False
            cursor.execute(
                "UPDATE current_polls SET state = 'open' "
                "WHERE unique_id = ? AND state IN ('failed', 'completing')",
                (unique_id,),
            )
            updated = cursor.rowcount == 1
            if updated:
                conn.commit()
            else:
                conn.rollback()
            return updated
        except sqlite3.Error:
            conn.rollback()
            return False
        finally:
            conn.close()

    def mark_failed(self, unique_id: str) -> bool:
        """Transition ``completing`` → ``failed``.

        Args:
            unique_id: Logical poll primary key.

        Returns:
            True when the row was updated from ``completing``.
        """
        return self._conditional_state_update(
            unique_id, from_state="completing", to_state="failed"
        )

    def mark_completed(self, unique_id: str) -> bool:
        """Transition ``completing`` → ``completed``.

        Args:
            unique_id: Logical poll primary key.

        Returns:
            True when the row was updated from ``completing``.
        """
        return self._conditional_state_update(
            unique_id, from_state="completing", to_state="completed"
        )

    def delete_completed(self, unique_id: str) -> bool:
        """Delete a poll only when its durable state is ``completed``.

        Args:
            unique_id: Logical poll primary key.

        Returns:
            True when a completed row was deleted.
        """
        conn = sqlite3.connect(self.dbname, timeout=5.0)
        try:
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                return False
            cursor.execute(
                "DELETE FROM current_polls WHERE unique_id = ? AND state = 'completed'",
                (unique_id,),
            )
            deleted = cursor.rowcount == 1
            if deleted:
                conn.commit()
            else:
                conn.rollback()
            return deleted
        except sqlite3.Error:
            conn.rollback()
            return False
        finally:
            conn.close()

    def _conditional_state_update(
        self, unique_id: str, *, from_state: str, to_state: str
    ) -> bool:
        """Apply a guarded lifecycle transition under ``BEGIN IMMEDIATE``.

        Args:
            unique_id: Logical poll primary key.
            from_state: Required current state.
            to_state: Target state.

        Returns:
            True when exactly one row was updated.
        """
        conn = sqlite3.connect(self.dbname, timeout=5.0)
        try:
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                return False
            cursor.execute(
                "UPDATE current_polls SET state = ? "
                "WHERE unique_id = ? AND state = ?",
                (to_state, unique_id, from_state),
            )
            updated = cursor.rowcount == 1
            if updated:
                conn.commit()
            else:
                conn.rollback()
            return updated
        except sqlite3.Error:
            conn.rollback()
            return False
        finally:
            conn.close()

    # --- Legacy poll helpers (remove message-only paths after T03) ----------

    def get_all_polls(self) -> list[PollRow]:
        """Return every poll row (including non-open states).

        Returns:
            All projected poll tuples.
        """
        with SQLWrapper(self.dbname) as sql_wrapper:
            return self._fetch_polls(sql_wrapper.cursor, "", ())

    def add_poll(self, *args) -> None:
        """Insert a new open poll (legacy 10-field positional args).

        Args:
            *args: ``unique_id, message_id, type, chat_id, buttons, timer, data,
                votes_need, hidden, thread_id``.
        """
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute(
                """INSERT INTO current_polls (
                    unique_id, message_id, type, chat_id, buttons, timer, data,
                    votes_need, hidden, thread_id, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
                args,
            )

    def get_poll(self, message_id: int) -> list[PollRow]:
        """Legacy message-only lookup; fail closed on cross-chat ambiguity.

        Removal condition: delete after T03 migrates every caller to
        :meth:`get_open_poll` (or another chat-aware API). Never picks a
        ``LIMIT 1`` winner when multiple chats share the same ``message_id``.

        Args:
            message_id: Telegram message id without chat scope.

        Returns:
            Matching rows when exactly one exists; empty list when none or
            when more than one chat shares the message id.
        """
        with SQLWrapper(self.dbname) as sql_wrapper:
            records = self._fetch_polls(
                sql_wrapper.cursor, "message_id = ?", (message_id,)
            )
            if len(records) > 1:
                chat_ids = sorted({row[3] for row in records})
                unique_ids = sorted(row[0] for row in records)
                logging.error(
                    "%s category=%s message_id=%s chat_ids=%s unique_ids=%s",
                    "message-only poll lookup ambiguous",
                    _LOG_GET_POLL_AMBIGUOUS,
                    message_id,
                    chat_ids,
                    unique_ids,
                )
                return []
            return records

    def get_message_id(self, unique_id: str):
        """Return ``message_id`` for a logical poll, if present.

        Args:
            unique_id: Logical poll primary key.

        Returns:
            Message id or ``None``.
        """
        with SQLWrapper(self.dbname) as sql_wrapper:
            records = self._fetch_polls(
                sql_wrapper.cursor, "unique_id = ?", (unique_id,)
            )
            if records:
                return records[0][1]
            return None

    def update_poll_votes(self, unique_id: str, buttons_scheme: str) -> None:
        """Legacy non-atomic buttons write (prefer :meth:`apply_vote`).

        Args:
            unique_id: Logical poll primary key.
            buttons_scheme: Serialized buttons JSON.
        """
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute(
                """UPDATE current_polls SET buttons = ? where unique_id = ?""",
                (buttons_scheme, unique_id),
            )

    def rem_rec(self, unique_id: str) -> None:
        """Legacy unconditional delete by ``unique_id``.

        Lifecycle progression and terminal completed deletion must use
        :meth:`claim_completion`, :meth:`mark_failed`, :meth:`mark_completed`,
        and :meth:`delete_completed`. Callers migrate away in T02/T03.

        Args:
            unique_id: Logical poll primary key.
        """
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute(
                """DELETE FROM current_polls WHERE unique_id = ?""", (unique_id,)
            )

    def abuse_update(self, user_id, timer=1800, force=False):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM abuse WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                sql_wrapper.cursor.execute("""INSERT INTO abuse VALUES (?,?,?);""", (user_id, int(time.time()), timer))
            elif not force:
                sql_wrapper.cursor.execute("""UPDATE abuse SET start_time = ?, timer = ? WHERE user_id = ?""",
                                           (int(time.time()), record[0][2] * 2, user_id))
            else:
                sql_wrapper.cursor.execute("""UPDATE abuse SET start_time = ?, timer = ? WHERE user_id = ?""",
                                           (int(time.time()), timer, user_id))

    def abuse_remove(self, user_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM abuse WHERE user_id = ?""", (user_id,))

    def abuse_check(self, user_id, force=False):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM abuse WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return 0, 0
            if record[0][1] + record[0][2] < int(time.time()) and not force:
                return 0, 0
            else:
                return record[0][1], record[0][2]

    def whitelist(self, user_id, add=False, remove=False):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM whitelist WHERE user_id = ?""", (user_id,))
            fetchall = sql_wrapper.cursor.fetchall()
            is_white = False
            if fetchall:
                if remove:
                    sql_wrapper.cursor.execute("""DELETE FROM whitelist WHERE user_id = ?""", (user_id,))
                else:
                    is_white = True
            if add and not fetchall:
                sql_wrapper.cursor.execute("""INSERT INTO whitelist VALUES (?);""", (user_id,))
                is_white = True
            return is_white

    def whitelist_get_all(self):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM whitelist""")
            fetchall = sql_wrapper.cursor.fetchall()
            return fetchall

    def mailing(self, user_id, add=False, remove=False):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM mailing WHERE user_id = ?""", (user_id,))
            fetchall = sql_wrapper.cursor.fetchall()
            is_mailing = False
            if fetchall:
                if remove:
                    sql_wrapper.cursor.execute("""DELETE FROM mailing WHERE user_id = ?""", (user_id,))
                else:
                    is_mailing = True
            if add and not fetchall:
                sql_wrapper.cursor.execute("""INSERT INTO mailing VALUES (?);""", (user_id,))
                is_mailing = True
            return is_mailing

    def mailing_get_all(self):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM mailing""")
            fetchall = sql_wrapper.cursor.fetchall()
            return fetchall

    def get_rate(self, user_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM rating WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                sql_wrapper.cursor.execute("""INSERT INTO rating VALUES (?,?)""", (user_id, 0))
                return 0
            return record[0][1]

    def get_all_rates(self):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM rating""")
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return None
            return record

    def update_rate(self, user_id, change):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM rating WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                sql_wrapper.cursor.execute("""INSERT INTO rating VALUES (?,?)""", (user_id, change))
            else:
                sql_wrapper.cursor.execute("""UPDATE rating SET rate = ? where user_id = ?""",
                                           (record[0][1] + change, user_id))

    def clear_rate(self, user_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM rating WHERE user_id = ?""", (user_id,))

    def get_ally(self, chat_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM allies WHERE chat_id = ?""", (chat_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return None
            return record[0]

    def get_allies(self):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM allies""")
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return []
            return record

    def add_ally(self, chat_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""INSERT INTO allies VALUES (?)""", (chat_id,))

    def remove_ally(self, chat_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM allies WHERE chat_id = ?""", (chat_id,))

    def abuse_random(self, chat_id, change=None):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM abuse_random WHERE chat_id = ?""", (chat_id,))
            record = sql_wrapper.cursor.fetchall()
            if change is not None:
                if not record:
                    sql_wrapper.cursor.execute("""INSERT INTO abuse_random VALUES (?,?)""", (chat_id, change))
                else:
                    sql_wrapper.cursor.execute("""UPDATE abuse_random SET abuse_random = ? where chat_id = ?""",
                                               (change, chat_id))
            if not record:
                return 0
            return record[0][1]

    def params(self, key, rewrite_value=None, default_return=None):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM params""")
            record: dict = json.loads(sql_wrapper.cursor.fetchall()[0][0])
            return_value = record.get(key, default_return)
            if rewrite_value is not None:
                record.update({key: rewrite_value})
                sql_wrapper.cursor.execute("""UPDATE params SET params = ?""", (json.dumps(record),))
            return return_value

    def captcha(self, message_id, add=False, remove=False, user_id=None, max_value=None, username=None):
        with SQLWrapper(self.dbname) as sql_wrapper:
            if add:
                sql_wrapper.cursor.execute("""INSERT INTO captcha VALUES (?, ?, ?, ?)""",
                                           (message_id, user_id, max_value, username))
                return None
            elif remove:
                sql_wrapper.cursor.execute("""DELETE FROM captcha WHERE message_id = ?""", (message_id,))
                return None
            elif user_id:
                sql_wrapper.cursor.execute("""SELECT * FROM captcha WHERE user_id = ?""", (user_id,))
                return sql_wrapper.cursor.fetchall()
            else:
                sql_wrapper.cursor.execute("""SELECT * FROM captcha WHERE message_id = ?""", (message_id,))
                return sql_wrapper.cursor.fetchall()

    def marmalade_add(self, user_id, entry_time):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM marmalade WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                sql_wrapper.cursor.execute("""INSERT INTO marmalade VALUES (?, ?)""",
                                           (user_id, entry_time))
            else:
                sql_wrapper.cursor.execute("""UPDATE marmalade SET entry_time = ? WHERE user_id = ?""",
                                           (entry_time, user_id))
            return None

    def marmalade_get(self, user_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM marmalade WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if record:
                return record[0][1]
            return None

    def marmalade_remove(self, user_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM marmalade WHERE user_id = ?""", (user_id,))
            return None
