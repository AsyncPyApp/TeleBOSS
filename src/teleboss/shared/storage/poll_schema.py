"""``current_polls`` DDL, schema init, and legacy migration helpers."""

import logging
import sqlite3
from typing import Final

from teleboss.shared.storage.poll_types import (
    PollMigrationError,
    _LOG_DUPLICATE_COMPOSITE,
    _LOG_MIGRATION_FAILED,
    _LOG_NULL_IDENTITY,
)

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


class PollSchemaMixin:
    """Mixin providing ``current_polls`` create/migrate helpers for :class:`SqlWorker`."""

    dbname: str

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
