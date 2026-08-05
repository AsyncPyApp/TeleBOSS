"""SQLite connection context manager for host storage."""

import sqlite3


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
