"""Plugin loader absent-dir path, discovery strings, .update() invariants."""

from __future__ import annotations

from helpers import REPO_ROOT


def test_loader_file_location() -> None:
    assert (REPO_ROOT / "src/teleboss/plugin_loader/loader.py").is_file()


def test_discovery_and_fail_closed_source_strings() -> None:
    loader_src = (REPO_ROOT / "src/teleboss/plugin_loader/loader.py").read_text(encoding="utf-8")
    assert 'plugin_folder = "plugins"' in loader_src
    assert "plugin_folder = data.path[:-1] + '_plugins'" in loader_src
    assert "f'{package_name}.{plugin_name}'" in loader_src
    assert "os.path.abspath(plugin_folder)" in loader_src
    assert 'PLUGIN_ENTRY_POINT_GROUP = "teleboss.plugins"' in loader_src
    assert loader_src.count("sys.exit(1)") >= 3
    assert "def forbidden_dec_in_plug" in loader_src
    assert "@bot." in loader_src
    assert "@utils.bot." in loader_src
    assert "PollEngine.post_vote_list.update(plugin_class.vote_list)" in loader_src
    assert "post_vote_list =" not in loader_src.replace(
        "PollEngine.post_vote_list.update", ""
    )


def test_absent_plugins_folder_empty_commands(runtime_data, poll_engine_snapshot) -> None:
    import shutil
    from pathlib import Path

    from teleboss.plugin_loader.loader import Plugins

    leftover = Path(runtime_data.path[:-1] + "_plugins")
    if leftover.is_dir():
        shutil.rmtree(leftover)
    assert Plugins.resolve_plugin_directory() is None

    inst = Plugins({})
    assert getattr(inst, "commands_final_dict", None) == {}
    assert not getattr(runtime_data, "plugins", None)


def test_post_vote_list_update_preserves_identity(poll_engine_snapshot) -> None:
    PollEngine = poll_engine_snapshot["PollEngine"]
    pvl_before = PollEngine.post_vote_list
    marker = object()
    PollEngine.post_vote_list.update({"__t02_marker__": marker})
    assert PollEngine.post_vote_list is pvl_before
    assert PollEngine.post_vote_list["__t02_marker__"] is marker
    del PollEngine.post_vote_list["__t02_marker__"]


def test_plugins_construct_keeps_post_vote_list(poll_engine_snapshot) -> None:
    from teleboss.app.commands import BuildInCommands
    from teleboss.domain import postvote_registry
    from teleboss.plugin_loader.loader import Plugins

    PollEngine = poll_engine_snapshot["PollEngine"]
    pvl_before = PollEngine.post_vote_list
    postvote_registry.post_vote_list_init()
    cmds_before = set(PollEngine.post_vote_list)
    plugins = Plugins(BuildInCommands().built_in_commands_dict)
    assert plugins is not None
    assert PollEngine.post_vote_list is pvl_before
    assert set(PollEngine.post_vote_list) == cmds_before
