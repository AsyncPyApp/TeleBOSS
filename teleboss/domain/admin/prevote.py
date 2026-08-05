"""Domain prevote barrel — stable ``teleboss.domain.admin.prevote.<Class>`` re-exports."""

from teleboss.domain.admin.prevote_op import OpSetup, Op, OpGlobal
from teleboss.domain.admin.prevote_roles import Rank, Deop
from teleboss.domain.admin.prevote_chat_meta import RemoveTopic, Title, Description, Avatar

__all__ = [
    "OpSetup",
    "Op",
    "OpGlobal",
    "RemoveTopic",
    "Rank",
    "Deop",
    "Title",
    "Description",
    "Avatar",
]
