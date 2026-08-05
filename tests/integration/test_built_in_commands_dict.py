"""BuildInCommands dict shape: primary keys, aliases, callable Command funcs."""

from __future__ import annotations

from helpers import BUILDIN_EXPECTED_KEYS
from teleboss.shared.command import Command


def test_built_in_commands_dict_aliases_and_callables(teleboss_runtime) -> None:
    from teleboss.app.commands import BuildInCommands

    cmds = BuildInCommands().built_in_commands_dict
    assert len(cmds) == len(BUILDIN_EXPECTED_KEYS)
    assert set(cmds) == set(BUILDIN_EXPECTED_KEYS)

    alias_map = {
        "ban": "banuser",
        "kick": "kickuser",
        "unmute": "unban",
        "random": "redrum",
    }
    for primary, alias in alias_map.items():
        assert cmds[primary].aliases == (alias,), primary

    for name, cmd in cmds.items():
        assert isinstance(cmd, Command), name
        assert callable(cmd.command_func), name
        # Do not invoke handlers (would hit Telegram / chat side effects).
