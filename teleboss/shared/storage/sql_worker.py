"""SQLite storage facade for TeleBOSS polls and host tables.

Public import path remains ``teleboss.shared.storage.sql_worker``. Logic lives in
concern modules composed via mixins; callers keep importing from this module.

``current_polls`` uses ``unique_id`` as the logical primary key and
``(chat_id, message_id)`` as the displayed-poll identity. Lifecycle state is
stored in ``state`` (offset 10). Tuple offsets 0–9 remain stable for legacy
callers.
"""

import sqlite3

from teleboss.shared.storage.host_tables import HostTablesMixin
from teleboss.shared.storage.poll_repository import PollRepositoryMixin
from teleboss.shared.storage.poll_schema import PollSchemaMixin
from teleboss.shared.storage.poll_types import (
    ApplyVoteResult,
    ApplyVoteStatus,
    PollMigrationError,
    PollRow,
    VoteMutator,
)
from teleboss.shared.storage.sql_connection import SQLWrapper

__all__ = [
    "ApplyVoteResult",
    "ApplyVoteStatus",
    "PollMigrationError",
    "PollRow",
    "SQLWrapper",
    "SqlWorker",
    "VoteMutator",
]


class SqlWorker(PollSchemaMixin, PollRepositoryMixin, HostTablesMixin):
    """Host SQLite facade composing poll schema, repository, and host tables."""

    dbname = ""

    def __init__(self, dbname: str, recommended) -> None:
        """Open or create the database and ensure poll + host schemas.

        Args:
            dbname: Path to the SQLite database file.
            recommended: Default JSON-serializable params seed when empty.
        """
        self.dbname = dbname

        sqlite_connection = sqlite3.connect(dbname)
        cursor = sqlite_connection.cursor()
        try:
            self._ensure_current_polls_schema(sqlite_connection, cursor)
            self._ensure_host_tables(cursor, recommended)
            sqlite_connection.commit()
        except Exception:
            sqlite_connection.rollback()
            raise
        finally:
            cursor.close()
            sqlite_connection.close()
