"""Dual-mode plugin discovery: directory, entry_points, both+dedupe."""

from __future__ import annotations

import importlib.util
import logging
import sys
import textwrap
from pathlib import Path

import pytest

from _t05_ep_fakes import FakeEP, make_ep_plugin_class

_SIMPLE_PLUGIN_SRC = textwrap.dedent(
    '''\
    from teleboss.shared.command import Command

    class Plugin:
        def __init__(self, built_in_commands):
            self.meta_info = {{
                "name": "{meta_name}",
                "type": "simple",
                "version-min": "1.0",
                "version-target": "99.0",
                "description": "{description}",
            }}
            self.plugin_commands_dict = {{
                "{cmd}": Command(command_func=self._cmd, aliases=None),
            }}

        def _cmd(self, *args, **kwargs):
            return None
    '''
)

# Split so this test module has no physical line starting with
# @bot.message_handler(commands= (EP fakes live in _t05_ep_fakes.py anyway).
_FORBIDDEN_PLUGIN_SRC = (
    "from teleboss.shared.command import Command\n\n"
    "@"
    'bot.message_handler(commands=["x"])\n'
    "def _bad():\n"
    "    pass\n\n"
    "class Plugin:\n"
    "    def __init__(self, built_in_commands):\n"
    "        self.meta_info = {\n"
    '            "name": "forbidden_plug",\n'
    '            "type": "simple",\n'
    '            "version-min": "1.0",\n'
    '            "version-target": "99.0",\n'
    '            "description": "should not load",\n'
    "        }\n"
    "        self.plugin_commands_dict = {\n"
    '            "forbidden_cmd": Command(command_func=self._cmd, aliases=None),\n'
    "        }\n\n"
    "    def _cmd(self, *args, **kwargs):\n"
    "        return None\n"
)


def _host_plugins_dir(runtime_data) -> Path:
    return Path(runtime_data.path[:-1] + "_plugins")


def _write_plugin(plugin_dir: Path, module_name: str, source: str) -> Path:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    path = plugin_dir / f"{module_name}.py"
    path.write_text(source, encoding="utf-8")
    return path


def _purge_plugin_modules(package_name: str, *module_names: str) -> None:
    for name in module_names:
        sys.modules.pop(f"{package_name}.{name}", None)
    sys.modules.pop(package_name, None)


def _cleanup_plugin_dir(plugin_dir: Path, *module_names: str) -> None:
    """Remove test plugin modules, ``__pycache__``, and empty plugin dir."""
    _purge_plugin_modules(plugin_dir.name, *module_names)
    for name in module_names:
        target = plugin_dir / f"{name}.py"
        if target.is_file():
            target.unlink()
    cache_dir = plugin_dir / "__pycache__"
    if cache_dir.is_dir():
        for cached in cache_dir.iterdir():
            cached.unlink(missing_ok=True)
        cache_dir.rmdir()
    if plugin_dir.is_dir() and not any(plugin_dir.iterdir()):
        plugin_dir.rmdir()


@pytest.fixture
def _restore_plugins_mode(runtime_data):
    previous = runtime_data.plugins_mode
    previous_plugins = dict(getattr(runtime_data, "plugins", None) or {})
    yield runtime_data
    runtime_data.plugins_mode = previous
    runtime_data.plugins = previous_plugins


def test_ep_fake_plugin_module_is_isolated() -> None:
    """FakeEP Plugin classes must not inherit this test file's ``__file__``."""
    ep_cls = make_ep_plugin_class("iso", "iso_cmd")
    assert ep_cls.__module__ == "_t05_ep_fakes"
    mod = sys.modules[ep_cls.__module__]
    assert Path(mod.__file__).name == "_t05_ep_fakes.py"
    # Helper must stay free of forbidden decorator source lines.
    helper_src = Path(mod.__file__).read_text(encoding="utf-8")
    for line in helper_src.splitlines():
        lt = line.lstrip()
        assert not lt.startswith("@bot.message_handler(commands=")
        assert not lt.startswith("@utils.bot.message_handler(commands=")


def test_config_plugins_mode_default_directory(runtime_data) -> None:
    assert runtime_data.plugins_mode == "directory"


def test_resolve_plugin_directory_absolute(_restore_plugins_mode, poll_engine_snapshot) -> None:
    from teleboss.plugin_loader.loader import Plugins

    runtime_data = _restore_plugins_mode
    plugin_dir = _host_plugins_dir(runtime_data)
    mod_name = "t05_abs_probe"
    try:
        _write_plugin(
            plugin_dir,
            mod_name,
            _SIMPLE_PLUGIN_SRC.format(
                meta_name="abs_probe",
                description="abs",
                cmd="abs_probe_cmd",
            ),
        )
        resolved = Plugins.resolve_plugin_directory()
        assert resolved is not None
        assert Path(resolved).is_absolute()
        assert Path(resolved) == plugin_dir.resolve()
    finally:
        _cleanup_plugin_dir(plugin_dir, mod_name)


def test_directory_mode_loads_plugin(
    _restore_plugins_mode,
    poll_engine_snapshot,
) -> None:
    from teleboss.plugin_loader.loader import Plugins

    runtime_data = _restore_plugins_mode
    runtime_data.plugins_mode = "directory"
    plugin_dir = _host_plugins_dir(runtime_data)
    mod_name = "t05_dir_only"
    try:
        _write_plugin(
            plugin_dir,
            mod_name,
            _SIMPLE_PLUGIN_SRC.format(
                meta_name="dir_only",
                description="directory plugin",
                cmd="dir_only_cmd",
            ),
        )
        inst = Plugins({})
        assert "dir_only_cmd" in inst.commands_final_dict
        assert runtime_data.plugins.get("dir_only") == "directory plugin"
    finally:
        _cleanup_plugin_dir(plugin_dir, mod_name)


def test_entry_points_mode_loads_plugin(
    _restore_plugins_mode,
    poll_engine_snapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from teleboss.plugin_loader import loader as loader_mod
    from teleboss.plugin_loader.loader import Plugins

    runtime_data = _restore_plugins_mode
    runtime_data.plugins_mode = "entry_points"
    ep_cls = make_ep_plugin_class("ep_only", "ep_only_cmd", "entry point plugin")
    monkeypatch.setattr(
        loader_mod.importlib_metadata,
        "entry_points",
        lambda group=None: (FakeEP("ep_only", ep_cls),) if group == "teleboss.plugins" else (),
    )
    inst = Plugins({})
    assert "ep_only_cmd" in inst.commands_final_dict
    assert runtime_data.plugins.get("ep_only") == "entry point plugin"


def test_both_mode_directory_wins_on_meta_name_conflict(
    _restore_plugins_mode,
    poll_engine_snapshot,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Directory wins via meta-name dedupe, not forbidden_dec rejecting the EP."""
    from teleboss.plugin_loader import loader as loader_mod
    from teleboss.plugin_loader.loader import Plugins

    runtime_data = _restore_plugins_mode
    runtime_data.plugins_mode = "both"
    plugin_dir = _host_plugins_dir(runtime_data)
    mod_name = "t05_both_dir"
    ep_cls = make_ep_plugin_class(
        "shared_name",
        "ep_shared_cmd",
        "from entry point",
    )
    # Prove the EP target itself is loadable when not deduped.
    runtime_data.plugins_mode = "entry_points"
    monkeypatch.setattr(
        loader_mod.importlib_metadata,
        "entry_points",
        lambda group=None: (
            (FakeEP("shared_ep", ep_cls),) if group == "teleboss.plugins" else ()
        ),
    )
    ep_only = Plugins({})
    assert "ep_shared_cmd" in ep_only.commands_final_dict
    runtime_data.plugins = {}

    runtime_data.plugins_mode = "both"
    try:
        _write_plugin(
            plugin_dir,
            mod_name,
            _SIMPLE_PLUGIN_SRC.format(
                meta_name="shared_name",
                description="from directory",
                cmd="dir_shared_cmd",
            ),
        )
        with caplog.at_level(logging.INFO):
            inst = Plugins({})
        assert "dir_shared_cmd" in inst.commands_final_dict
        assert "ep_shared_cmd" not in inst.commands_final_dict
        assert runtime_data.plugins.get("shared_name") == "from directory"
        skip_msgs = [
            r.getMessage()
            for r in caplog.records
            if "already loaded from directory" in r.getMessage()
        ]
        assert skip_msgs, "expected dedupe skip log, got no directory-wins message"
        assert any("shared_name" in msg for msg in skip_msgs)
    finally:
        _cleanup_plugin_dir(plugin_dir, mod_name)


def test_forbidden_decorator_still_blocks_directory_plugin(
    _restore_plugins_mode,
    poll_engine_snapshot,
) -> None:
    from teleboss.plugin_loader.loader import Plugins

    runtime_data = _restore_plugins_mode
    runtime_data.plugins_mode = "directory"
    plugin_dir = _host_plugins_dir(runtime_data)
    mod_name = "t05_forbidden"
    try:
        _write_plugin(plugin_dir, mod_name, _FORBIDDEN_PLUGIN_SRC)
        inst = Plugins({})
        assert "forbidden_cmd" not in inst.commands_final_dict
        assert "forbidden_plug" not in (runtime_data.plugins or {})
    finally:
        _cleanup_plugin_dir(plugin_dir, mod_name)


def test_valid_plugins_modes_constant() -> None:
    from teleboss.plugin_loader.loader import (
        PLUGIN_ENTRY_POINT_GROUP,
        VALID_PLUGINS_MODES,
    )

    assert PLUGIN_ENTRY_POINT_GROUP == "teleboss.plugins"
    assert VALID_PLUGINS_MODES == frozenset({"directory", "entry_points", "both"})


def test_both_mode_loads_distinct_directory_and_ep(
    _restore_plugins_mode,
    poll_engine_snapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Union path: distinct meta names from directory and EP both register."""
    from teleboss.plugin_loader import loader as loader_mod
    from teleboss.plugin_loader.loader import Plugins

    runtime_data = _restore_plugins_mode
    runtime_data.plugins_mode = "both"
    plugin_dir = _host_plugins_dir(runtime_data)
    mod_name = "t05_both_union_dir"
    try:
        _write_plugin(
            plugin_dir,
            mod_name,
            _SIMPLE_PLUGIN_SRC.format(
                meta_name="union_dir",
                description="directory side",
                cmd="union_dir_cmd",
            ),
        )
        ep_cls = make_ep_plugin_class(
            "union_ep",
            "union_ep_cmd",
            "entry point side",
        )
        monkeypatch.setattr(
            loader_mod.importlib_metadata,
            "entry_points",
            lambda group=None: (
                (FakeEP("union_ep", ep_cls),)
                if group == "teleboss.plugins"
                else ()
            ),
        )
        inst = Plugins({})
        assert "union_dir_cmd" in inst.commands_final_dict
        assert "union_ep_cmd" in inst.commands_final_dict
        assert runtime_data.plugins.get("union_dir") == "directory side"
        assert runtime_data.plugins.get("union_ep") == "entry point side"
    finally:
        _cleanup_plugin_dir(plugin_dir, mod_name)


def test_entry_points_mode_ignores_directory_plugins(
    _restore_plugins_mode,
    poll_engine_snapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """entry_points mode must not scan the host plugin directory."""
    from teleboss.plugin_loader import loader as loader_mod
    from teleboss.plugin_loader.loader import Plugins

    runtime_data = _restore_plugins_mode
    runtime_data.plugins_mode = "entry_points"
    plugin_dir = _host_plugins_dir(runtime_data)
    mod_name = "t05_ep_ignores_dir"
    try:
        _write_plugin(
            plugin_dir,
            mod_name,
            _SIMPLE_PLUGIN_SRC.format(
                meta_name="should_ignore_dir",
                description="must stay unloaded",
                cmd="ignored_dir_cmd",
            ),
        )
        ep_cls = make_ep_plugin_class("ep_keep", "ep_keep_cmd", "kept")
        monkeypatch.setattr(
            loader_mod.importlib_metadata,
            "entry_points",
            lambda group=None: (
                (FakeEP("ep_keep", ep_cls),)
                if group == "teleboss.plugins"
                else ()
            ),
        )
        inst = Plugins({})
        assert "ep_keep_cmd" in inst.commands_final_dict
        assert "ignored_dir_cmd" not in inst.commands_final_dict
        assert "should_ignore_dir" not in (runtime_data.plugins or {})
        assert runtime_data.plugins.get("ep_keep") == "kept"
    finally:
        _cleanup_plugin_dir(plugin_dir, mod_name)


def test_forbidden_decorator_still_blocks_entry_point_plugin(
    _restore_plugins_mode,
    poll_engine_snapshot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """EP path still runs forbidden_dec_in_plug against the defining module file."""
    from teleboss.plugin_loader import loader as loader_mod
    from teleboss.plugin_loader.loader import Plugins

    runtime_data = _restore_plugins_mode
    runtime_data.plugins_mode = "entry_points"
    # Written to a temp module; split concat keeps THIS file scan-clean.
    ep_forbidden_src = (
        "from teleboss.shared.command import Command\n\n"
        "class _DummyBot:\n"
        "    def message_handler(self, **kwargs):\n"
        "        def _deco(fn):\n"
        "            return fn\n"
        "        return _deco\n\n"
        "bot = _DummyBot()\n\n"
        "@"
        'bot.message_handler(commands=["x"])\n'
        "def _bad():\n"
        "    pass\n\n"
        "class Plugin:\n"
        "    def __init__(self, built_in_commands):\n"
        "        self.meta_info = {\n"
        '            "name": "forbidden_plug",\n'
        '            "type": "simple",\n'
        '            "version-min": "1.0",\n'
        '            "version-target": "99.0",\n'
        '            "description": "should not load",\n'
        "        }\n"
        "        self.plugin_commands_dict = {\n"
        '            "forbidden_cmd": Command(command_func=self._cmd, aliases=None),\n'
        "        }\n\n"
        "    def _cmd(self, *args, **kwargs):\n"
        "        return None\n"
    )
    mod_file = tmp_path / "t05_ep_forbidden_mod.py"
    mod_file.write_text(ep_forbidden_src, encoding="utf-8")
    mod_name = "t05_ep_forbidden_mod"
    spec = importlib.util.spec_from_file_location(mod_name, mod_file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
        monkeypatch.setattr(
            loader_mod.importlib_metadata,
            "entry_points",
            lambda group=None: (
                (FakeEP("forbidden_ep", module.Plugin),)
                if group == "teleboss.plugins"
                else ()
            ),
        )
        inst = Plugins({})
        assert "forbidden_cmd" not in inst.commands_final_dict
        assert "forbidden_plug" not in (runtime_data.plugins or {})
    finally:
        sys.modules.pop(mod_name, None)


def test_unknown_plugins_mode_falls_back_to_directory(
    _restore_plugins_mode,
    poll_engine_snapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loader treats invalid mode as directory (warn + directory scan)."""
    from teleboss.plugin_loader import loader as loader_mod
    from teleboss.plugin_loader.loader import Plugins

    runtime_data = _restore_plugins_mode
    runtime_data.plugins_mode = "not-a-real-mode"
    plugin_dir = _host_plugins_dir(runtime_data)
    mod_name = "t05_fallback_dir"
    try:
        _write_plugin(
            plugin_dir,
            mod_name,
            _SIMPLE_PLUGIN_SRC.format(
                meta_name="fallback_dir",
                description="loaded via fallback",
                cmd="fallback_dir_cmd",
            ),
        )
        ep_cls = make_ep_plugin_class("fallback_ep", "fallback_ep_cmd", "should not load")
        monkeypatch.setattr(
            loader_mod.importlib_metadata,
            "entry_points",
            lambda group=None: (
                (FakeEP("fallback_ep", ep_cls),)
                if group == "teleboss.plugins"
                else ()
            ),
        )
        inst = Plugins({})
        assert "fallback_dir_cmd" in inst.commands_final_dict
        assert "fallback_ep_cmd" not in inst.commands_final_dict
        assert runtime_data.plugins.get("fallback_dir") == "loaded via fallback"
    finally:
        _cleanup_plugin_dir(plugin_dir, mod_name)
