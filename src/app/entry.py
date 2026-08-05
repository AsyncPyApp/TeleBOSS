"""Canonical process entry for TeleBOSS.

``main()`` owns the full bootstrap sequence (handler side-effect imports,
preflight before plugins, register, poll recovery, polling). Root ``main.py``
and the ``teleboss`` console script both delegate here.

Host workdir: ``ConfigData`` still reads optional ``sys.argv[1]`` as the data
directory when the process starts; this module does not rewrite argv or cwd.
"""

from teleboss.shared.python_floor import ensure_min_python

ensure_min_python()

from teleboss.app.commands import BuildInCommands
from teleboss.app.handlers import membership  # noqa: F401  # new_chat_members
from teleboss.app.handlers import captcha  # noqa: F401
from teleboss.app.handlers import votes  # noqa: F401  # cancel..user_votes, then op!, then vote!
from teleboss.app.handlers import help as help_handlers  # noqa: F401  # help!_cat, help!_main
from teleboss.domain.postvote_registry import post_vote_list_init
from teleboss.plugin_loader.loader import Plugins
from teleboss.shared.bootstrap import init, preflight_compatibility, register_commands
from teleboss.shared.runtime import bot
from teleboss.voting.engine import poll_engine


def main() -> None:
    """Run ordered bootstrap then block on Telegram long polling.

    Order is frozen: built-ins → post-vote registry → preflight → plugins →
    ``init`` → ``register_commands`` → ``auto_restart_polls`` → polling.
    """
    built_in_command_list = BuildInCommands().built_in_commands_dict
    post_vote_list_init()
    stored_version = preflight_compatibility()
    plugins_command_list = Plugins(built_in_command_list).commands_final_dict
    init(stored_version)
    register_commands(plugins_command_list, built_in_command_list)
    poll_engine.auto_restart_polls()
    bot.infinity_polling()


if __name__ == "__main__":
    main()
