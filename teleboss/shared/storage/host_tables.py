"""Non-poll host SQLite tables and helpers."""

import json
import sqlite3
import time

from teleboss.shared.storage.sql_connection import SQLWrapper


class HostTablesMixin:
    """Mixin providing host (non-poll) table helpers for :class:`SqlWorker`."""

    dbname: str

    def _ensure_host_tables(
        self, cursor: sqlite3.Cursor, recommended
    ) -> None:
        """Create host tables and seed ``params`` when empty.

        Args:
            cursor: Cursor on an open connection (caller owns commit).
            recommended: Default JSON-serializable params seed when empty.
        """
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

    def abuse_update(self, user_id, timer=1800, force=False):
        """Insert or refresh an abuse cooldown row for ``user_id``."""
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
        """Delete the abuse row for ``user_id``."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM abuse WHERE user_id = ?""", (user_id,))

    def abuse_check(self, user_id, force=False):
        """Return active abuse ``(start_time, timer)`` or ``(0, 0)`` if expired."""
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
        """Query or mutate whitelist membership for ``user_id``."""
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
        """Return all whitelist rows."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM whitelist""")
            fetchall = sql_wrapper.cursor.fetchall()
            return fetchall

    def mailing(self, user_id, add=False, remove=False):
        """Query or mutate mailing-list membership for ``user_id``."""
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
        """Return all mailing-list rows."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM mailing""")
            fetchall = sql_wrapper.cursor.fetchall()
            return fetchall

    def get_rate(self, user_id):
        """Return rating for ``user_id``, inserting ``0`` when missing."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM rating WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                sql_wrapper.cursor.execute("""INSERT INTO rating VALUES (?,?)""", (user_id, 0))
                return 0
            return record[0][1]

    def get_all_rates(self):
        """Return all rating rows, or ``None`` when empty."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM rating""")
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return None
            return record

    def update_rate(self, user_id, change):
        """Add ``change`` to the rating for ``user_id`` (insert if missing)."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM rating WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                sql_wrapper.cursor.execute("""INSERT INTO rating VALUES (?,?)""", (user_id, change))
            else:
                sql_wrapper.cursor.execute("""UPDATE rating SET rate = ? where user_id = ?""",
                                           (record[0][1] + change, user_id))

    def clear_rate(self, user_id):
        """Delete the rating row for ``user_id``."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM rating WHERE user_id = ?""", (user_id,))

    def get_ally(self, chat_id):
        """Return the allies row for ``chat_id``, or ``None``."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM allies WHERE chat_id = ?""", (chat_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return None
            return record[0]

    def get_allies(self):
        """Return all allies rows (empty list when none)."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM allies""")
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return []
            return record

    def add_ally(self, chat_id):
        """Insert ``chat_id`` into allies."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""INSERT INTO allies VALUES (?)""", (chat_id,))

    def remove_ally(self, chat_id):
        """Delete ``chat_id`` from allies."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM allies WHERE chat_id = ?""", (chat_id,))

    def abuse_random(self, chat_id, change=None):
        """Get or set the abuse_random value for ``chat_id``."""
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
        """Read or rewrite a key in the JSON ``params`` blob."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM params""")
            record: dict = json.loads(sql_wrapper.cursor.fetchall()[0][0])
            return_value = record.get(key, default_return)
            if rewrite_value is not None:
                record.update({key: rewrite_value})
                sql_wrapper.cursor.execute("""UPDATE params SET params = ?""", (json.dumps(record),))
            return return_value

    def captcha(self, message_id, add=False, remove=False, user_id=None, max_value=None, username=None):
        """Add, remove, or look up captcha rows."""
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
        """Insert or update a marmalade entry for ``user_id``."""
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
        """Return marmalade entry_time for ``user_id``, or ``None``."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM marmalade WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if record:
                return record[0][1]
            return None

    def marmalade_remove(self, user_id):
        """Delete the marmalade row for ``user_id``."""
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM marmalade WHERE user_id = ?""", (user_id,))
            return None
