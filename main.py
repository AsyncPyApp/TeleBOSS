"""Thin entry: ordered handler side-effect imports + bootstrap."""
import plugin_engine
import postvote
import utils
from poll_engines import poll_engine
from utils import bot

from teleboss.app.commands import BuildInCommands
from teleboss.app.handlers import membership  # noqa: F401  # new_chat_members
from teleboss.app.handlers import captcha  # noqa: F401
from teleboss.app.handlers import votes  # noqa: F401  # cancel..user_votes, then op!, then vote!
from teleboss.app.handlers import help as help_handlers  # noqa: F401  # help!_cat, help!_main


if __name__ == "__main__":
    built_in_command_list = BuildInCommands().built_in_commands_dict
    postvote.post_vote_list_init()
    plugins_command_list = plugin_engine.Plugins(built_in_command_list).commands_final_dict
    utils.init()
    utils.register_commands(plugins_command_list, built_in_command_list)
    poll_engine.auto_restart_polls()
    bot.infinity_polling()
