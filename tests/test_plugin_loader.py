"""Plugin loader absent-dir path, discovery strings, .update() invariants."""

from __future__ import annotations

import os

from helpers import REPO_ROOT


def test_loader_file_location() -> None:
    assert (REPO_ROOT / "teleboss/plugin_loader/loader.py").is_file()


def test_discovery_and_fail_closed_source_strings() -> None:
    loader_src = (REPO_ROOT / "teleboss/plugin_loader/loader.py").read_text(encoding="utf-8")
    assert 'plugin_folder = "plugins"' in loader_src
    assert "plugin_folder = data.path[:-1] + '_plugins'" in loader_src
    assert "f'{plugin_folder}.{plugin_name}'" in loader_src
    assert loader_src.count("sys.exit(1)") >= 3
    assert "def forbidden_dec_in_plug" in loader_src
    assert "@bot." in loader_src
    assert "@utils.bot." in loader_src
    assert "PollEngine.post_vote_list.update(plugin_class.vote_list)" in loader_src
    assert "post_vote_list =" not in loader_src.replace(
        "PollEngine.post_vote_list.update", ""
    )


def test_absent_plugins_folder_empty_commands(utils_mod, poll_engine_snapshot) -> None:
    import plugin_engine

    plugin_folder = "plugins"
    if utils_mod.data.path:
        plugin_folder = utils_mod.data.path[:-1] + "_plugins"
    assert not os.path.isdir(plugin_folder), f"unexpected plugin folder {plugin_folder!r}"

    inst = plugin_engine.Plugins({})
    assert getattr(inst, "commands_final_dict", None) == {}
    assert not getattr(utils_mod.data, "plugins", None)


def test_post_vote_list_update_preserves_identity(poll_engine_snapshot) -> None:
    PollEngine = poll_engine_snapshot["PollEngine"]
    pvl_before = PollEngine.post_vote_list
    marker = object()
    PollEngine.post_vote_list.update({"__t02_marker__": marker})
    assert PollEngine.post_vote_list is pvl_before
    assert PollEngine.post_vote_list["__t02_marker__"] is marker
    del PollEngine.post_vote_list["__t02_marker__"]


def test_plugins_construct_keeps_post_vote_list(utils_mod, poll_engine_snapshot) -> None:
    import postvote
    from teleboss.app.commands import BuildInCommands
    from teleboss.plugin_loader.loader import Plugins

    PollEngine = poll_engine_snapshot["PollEngine"]
    pvl_before = PollEngine.post_vote_list
    postvote.post_vote_list_init()
    cmds_before = set(PollEngine.post_vote_list)
    plugins = Plugins(BuildInCommands().built_in_commands_dict)
    assert plugins is not None
    assert PollEngine.post_vote_list is pvl_before
    assert set(PollEngine.post_vote_list) == cmds_before
