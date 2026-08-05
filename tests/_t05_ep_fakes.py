"""Clean FakeEP Plugin helpers for T05 dual-mode tests.

This module must stay free of forbidden ``@bot.message_handler(commands=``
source lines so EP Plugin ``__module__`` / ``__file__`` never poison
``forbidden_dec_in_plug`` scans during directory-wins / EP load tests.
"""

from __future__ import annotations

from teleboss.shared.command import Command


class FakeEP:
    """Minimal entry-point stand-in for offline tests."""

    def __init__(self, name: str, target):
        self.name = name
        self._target = target

    def load(self):
        """Return the registered entry-point target."""
        return self._target


def make_ep_plugin_class(
    meta_name: str,
    cmd: str,
    description: str = "ep plugin",
):
    """Build a Plugin class with ``__module__`` bound to this clean file.

    Args:
        meta_name: Plugin ``meta_info['name']``.
        cmd: Primary command key to register.
        description: Plugin ``meta_info['description']``.

    Returns:
        A Plugin class constructible like directory plugins.
    """

    class Plugin:
        def __init__(self, built_in_commands):
            self.meta_info = {
                "name": meta_name,
                "type": "simple",
                "version-min": "1.0",
                "version-target": "99.0",
                "description": description,
            }
            self.plugin_commands_dict = {
                cmd: Command(command_func=self._cmd, aliases=None),
            }

        def _cmd(self, *args, **kwargs):
            return None

    return Plugin
