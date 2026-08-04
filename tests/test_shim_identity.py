"""Shim ↔ canonical object identity (deduped from _t03–_t09)."""

from __future__ import annotations


def test_utils_runtime_identity(utils_mod, teleboss_runtime) -> None:
    from teleboss.shared import command as command_mod
    from teleboss.shared import config as config_mod
    from teleboss.shared import parsers

    assert utils_mod.data is teleboss_runtime.data
    assert utils_mod.bot is teleboss_runtime.bot
    assert utils_mod.sqlWorker is teleboss_runtime.sqlWorker
    assert utils_mod.helper is teleboss_runtime.helper
    assert utils_mod.Command is command_mod.Command
    assert config_mod.bot is utils_mod.bot
    assert config_mod.sqlWorker is utils_mod.sqlWorker
    assert utils_mod.html_fix is parsers.html_fix
    assert utils_mod.topic_reply_fix is parsers.topic_reply_fix


def test_sql_worker_get_bound(utils_mod) -> None:
    utils_mod.data.sql_worker_get()  # must not raise


def test_poll_engines_identity(utils_mod, poll_engine_snapshot) -> None:
    import poll_engines
    from teleboss.voting import bases as bases_mod
    from teleboss.voting import engine as engine_mod
    from teleboss.voting import exceptions as exc_mod

    exports = (
        "PollEngine",
        "poll_engine",
        "PreVote",
        "PostVote",
        "SilentException",
        "InternalBotException",
    )
    assert all(hasattr(poll_engines, n) for n in exports)
    assert set(getattr(poll_engines, "__all__", [])) == set(exports)
    assert poll_engines.poll_engine is engine_mod.poll_engine
    assert poll_engines.PollEngine is engine_mod.PollEngine
    assert poll_engines.PreVote is bases_mod.PreVote
    assert poll_engines.PostVote is bases_mod.PostVote
    assert poll_engines.SilentException is exc_mod.SilentException
    assert poll_engines.InternalBotException is exc_mod.InternalBotException
    assert poll_engines.PollEngine.post_vote_list is engine_mod.PollEngine.post_vote_list
    assert poll_engines.poll_engine.post_vote_list is engine_mod.PollEngine.post_vote_list
    assert poll_engine_snapshot["was_empty"]
    assert isinstance(engine_mod.PollEngine.post_vote_list, dict)


def test_plugin_engine_identity(utils_mod) -> None:
    import plugin_engine
    from teleboss.plugin_loader import loader as loader_mod
    from teleboss.shared.command import Command as SharedCommand
    from teleboss.shared.runtime import data as runtime_data

    exports = ("Plugins", "META_INFO_TEMPLATE")
    assert all(hasattr(plugin_engine, n) for n in exports)
    assert set(getattr(plugin_engine, "__all__", [])) == set(exports)
    assert plugin_engine.Plugins is loader_mod.Plugins
    assert plugin_engine.META_INFO_TEMPLATE is loader_mod.META_INFO_TEMPLATE
    assert SharedCommand is utils_mod.Command
    assert runtime_data is utils_mod.data


def test_sql_worker_shim_importable(utils_mod) -> None:
    import sql_worker

    assert sql_worker is not None


def test_consumer_module_bot_identity(utils_mod) -> None:
    import main
    import plugin_engine
    import poll_engines
    import postvote
    import prevote
    from teleboss.voting import bases as bases_mod
    from teleboss.voting import engine as engine_mod

    assert main.bot is utils_mod.bot

    for mod in (prevote, postvote, plugin_engine, main, poll_engines):
        if hasattr(mod, "bot"):
            assert mod.bot is utils_mod.bot
        if hasattr(mod, "Command"):
            assert mod.Command is utils_mod.Command
        if hasattr(mod, "poll_engine"):
            assert mod.poll_engine is engine_mod.poll_engine
        if hasattr(mod, "PollEngine"):
            assert mod.PollEngine is engine_mod.PollEngine
        if hasattr(mod, "PreVote"):
            assert mod.PreVote is bases_mod.PreVote
        if hasattr(mod, "PostVote"):
            assert mod.PostVote is bases_mod.PostVote
