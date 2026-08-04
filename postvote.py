"""Compatibility shim: PostVote catalog + post_vote_list_init."""
from teleboss.domain.admin.postvote import (
    ChatPic,
    Deop,
    Description,
    GlobalOp,
    GlobalOpSetup,
    Op,
    OpSetup,
    Rank,
    Title,
    Topic,
)
from teleboss.domain.allies.postvote import AddAllies, RemoveAllies
from teleboss.domain.content.postvote import AddRules, CustomPoll, RemoveRules
from teleboss.domain.moderation.postvote import Ban, Captcha, DelMessage, UnBan, UserAdd
from teleboss.domain.postvote_registry import post_vote_list_init
from teleboss.domain.settings.postvote import (
    ChangeRate,
    Marmalade,
    PrivateMode,
    RandomCooldown,
    Shield,
    Threshold,
    Timer,
    TimerBan,
    VotePrivacy,
    Whitelist,
)

__all__ = [
    "UserAdd",
    "Ban",
    "UnBan",
    "Captcha",
    "DelMessage",
    "Threshold",
    "Timer",
    "TimerBan",
    "ChangeRate",
    "Whitelist",
    "PrivateMode",
    "Shield",
    "VotePrivacy",
    "Marmalade",
    "RandomCooldown",
    "GlobalOp",
    "OpSetup",
    "GlobalOpSetup",
    "Op",
    "Rank",
    "Deop",
    "Title",
    "Description",
    "ChatPic",
    "Topic",
    "AddAllies",
    "RemoveAllies",
    "AddRules",
    "RemoveRules",
    "CustomPoll",
    "post_vote_list_init",
]
