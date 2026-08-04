"""Compatibility shim: canonical package is teleboss.voting."""
from teleboss.voting.bases import PostVote, PreVote
from teleboss.voting.engine import PollEngine, poll_engine
from teleboss.voting.exceptions import InternalBotException, SilentException

__all__ = [
    "PollEngine",
    "poll_engine",
    "PreVote",
    "PostVote",
    "SilentException",
    "InternalBotException",
]
