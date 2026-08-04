"""Offline pure plugin-loader helpers + absent-dir empty dict regression."""

from __future__ import annotations

import os
from pathlib import Path

from teleboss.shared.command import Command


def test_meta_is_valid_complete_and_failures(teleboss_runtime) -> None:
    from teleboss.plugin_loader.loader import Plugins

    good = {
        "name": "demo",
        "type": "simple",
        "version-min": "3.0",
        "version-target": "3.3",
        "description": "demo plugin",
    }
    assert Plugins.meta_is_valid(good, "demo.py") is True
    assert Plugins.meta_is_valid("not-a-dict", "demo.py") is False  # type: ignore[arg-type]
    bad_missing = dict(good)
    del bad_missing["description"]
    assert Plugins.meta_is_valid(bad_missing, "demo.py") is False
    bad_type = dict(good)
    bad_type["version-min"] = 3  # type: ignore[assignment]
    assert Plugins.meta_is_valid(bad_type, "demo.py") is False


def test_get_all_prebuild_commands_expands_aliases(teleboss_runtime) -> None:
    from teleboss.plugin_loader.loader import Plugins

    def _noop():
        return None

    built = {
        "ban": Command(command_func=_noop, aliases=("banuser",)),
        "kick": Command(command_func=_noop, aliases=("kickuser",)),
        "help": Command(command_func=_noop, aliases=None),
    }
    expanded = Plugins.get_all_prebuild_commands(built)
    assert expanded == ["ban", "banuser", "kick", "kickuser", "help"]


def test_forbidden_dec_in_plug_tempfile(teleboss_runtime, tmp_path: Path) -> None:
    from teleboss.plugin_loader.loader import Plugins

    clean = tmp_path / "clean.py"
    clean.write_text("# ok\nplugin_commands_dict = {}\n", encoding="utf-8")
    assert Plugins.forbidden_dec_in_plug(str(clean)) is False

    bad_bot = tmp_path / "bad_bot.py"
    bad_bot.write_text('@bot.message_handler(commands=["x"])\ndef f():\n    pass\n', encoding="utf-8")
    assert Plugins.forbidden_dec_in_plug(str(bad_bot)) is True

    bad_utils = tmp_path / "bad_utils.py"
    bad_utils.write_text(
        '@utils.bot.message_handler(commands=["y"])\ndef g():\n    pass\n',
        encoding="utf-8",
    )
    assert Plugins.forbidden_dec_in_plug(str(bad_utils)) is True


def test_absent_plugins_dir_empty_commands_dict(utils_mod, poll_engine_snapshot) -> None:
    """Regression: missing plugins folder leaves commands_final_dict empty."""
    import plugin_engine

    plugin_folder = "plugins"
    if utils_mod.data.path:
        plugin_folder = utils_mod.data.path[:-1] + "_plugins"
    assert not os.path.isdir(plugin_folder), f"unexpected plugin folder {plugin_folder!r}"

    inst = plugin_engine.Plugins({})
    assert getattr(inst, "commands_final_dict", None) == {}
