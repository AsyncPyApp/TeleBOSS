"""Host-facing built-in command implementations (non-prevote)."""

from teleboss.app.host_commands.info import InfoMixin
from teleboss.app.host_commands.membership import MembershipMixin
from teleboss.app.host_commands.misc import MiscMixin
from teleboss.app.host_commands.moderation import ModerationMixin


class HostCommands(MembershipMixin, InfoMixin, ModerationMixin, MiscMixin):
    """Composed static handlers for non-prevote host commands."""
