"""Compatibility shim: PreVote catalog."""
from teleboss.domain.moderation.prevote import (
    Invite,
    Ban,
    Kick,
    Mute,
    Unban,
    MessageRemover,
    MessageSilentRemover,
    NewUserChecker,
)
from teleboss.domain.settings.prevote import (
    Thresholds,
    Timer,
    Rating,
    Whitelist,
    PrivateMode,
    Votes,
    Shield,
    Marmalade,
)
from teleboss.domain.admin.prevote import (
    OpSetup,
    Op,
    OpGlobal,
    RemoveTopic,
    Rank,
    Deop,
    Title,
    Description,
    Avatar,
)
from teleboss.domain.allies.prevote import AlliesList
from teleboss.domain.content.prevote import (
    Rules,
    CustomPoll,
)

__all__ = [
    "Invite",
    "Ban",
    "Kick",
    "Mute",
    "Unban",
    "MessageRemover",
    "MessageSilentRemover",
    "NewUserChecker",
    "Thresholds",
    "Timer",
    "Rating",
    "Whitelist",
    "PrivateMode",
    "Votes",
    "Shield",
    "Marmalade",
    "OpSetup",
    "Op",
    "OpGlobal",
    "RemoveTopic",
    "Rank",
    "Deop",
    "Title",
    "Description",
    "Avatar",
    "AlliesList",
    "Rules",
    "CustomPoll",
]
