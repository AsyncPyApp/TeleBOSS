"""Assemble PollEngine.post_vote_list from domain PostVote handlers."""
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
from teleboss.voting.engine import PollEngine


def post_vote_list_init():
    post_vote_list = {
        "invite": UserAdd(),
        "ban": Ban(),
        "unban": UnBan(),
        "threshold": Threshold(),
        "timer": Timer(),
        "timer for ban votes": TimerBan(),
        "delete message": DelMessage(),
        "op": Op(),
        "deop": Deop(),
        "title": Title(),
        "chat picture": ChatPic(),
        "description": Description(),
        "rank": Rank(),
        "captcha": Captcha(),
        "change rate": ChangeRate(),
        "add allies": AddAllies(),
        "remove allies": RemoveAllies(),
        "timer for random cooldown": RandomCooldown(),
        "whitelist": Whitelist(),
        "global op permissions": GlobalOp(),
        "private mode": PrivateMode(),
        "remove topic": Topic(),
        "add rules": AddRules(),
        "remove rules": RemoveRules(),
        "custom poll": CustomPoll(),
        "shield": Shield(),
        "marmalade": Marmalade(),
        "vote_privacy": VotePrivacy(),
        "global op setup": GlobalOpSetup(),
        "op setup": OpSetup(),
    }

    PollEngine.post_vote_list.update(post_vote_list)
