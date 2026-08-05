"""Shared poll storage types, constants, and vote-result models."""

from collections.abc import Callable
from enum import StrEnum
from typing import Final

# Stable SELECT projection: offsets 0–9 match the historical row layout; 10 is state.
_POLL_COLUMNS: Final = (
    "unique_id, message_id, type, chat_id, buttons, timer, data, "
    "votes_need, hidden, thread_id, state"
)

_RECOVERABLE_STATES: Final = frozenset({"open", "completing", "failed"})

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
