"""Poll CRUD, atomic vote mutation, and lifecycle APIs."""

import logging
import sqlite3

from teleboss.shared.storage.poll_types import (
    ApplyVoteResult,
    ApplyVoteStatus,
    PollRow,
    VoteMutator,
    _LOG_GET_POLL_AMBIGUOUS,
    _POLL_COLUMNS,
    _RECOVERABLE_STATES,
)
from teleboss.shared.storage.sql_connection import SQLWrapper


class PollRepositoryMixin:
    """Mixin providing poll repository methods for :class:`SqlWorker`."""

    dbname: str

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
