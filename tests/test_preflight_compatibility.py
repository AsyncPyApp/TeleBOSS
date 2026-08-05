"""Offline coverage for ``preflight_compatibility`` and poison-plugin ordering."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from helpers import REPO_ROOT

_SMOKE_TEMPLATE = REPO_ROOT / "tests" / "fixtures" / "smoke_config.ini.template"
_VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
_INCOMPATIBLE_VERSION = "3.0"


def test_preflight_compatible_returns_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compatible path runs deps → SQL hydrate → version read and returns snapshot."""
    from teleboss.shared import bootstrap

    order: list[str] = []

    def _deps() -> None:
        order.append("deps")

    def _hydrate() -> None:
        order.append("sql")

    def _params(key: str, default_return=None, rewrite_value=None):  # noqa: ANN001
        assert key == "version"
        assert rewrite_value is None
        order.append("version")
        return "4.0.0"

    monkeypatch.setattr(bootstrap, "check_dependency_versions", _deps)
    monkeypatch.setattr(bootstrap.data, "sql_worker_get", _hydrate)
    monkeypatch.setattr(bootstrap.sqlWorker, "params", _params)
    monkeypatch.setattr(bootstrap.data, "MIN_VERSION", "4.0")
    monkeypatch.setattr(bootstrap.data, "VERSION", "4.0.0")

    side_effect_guard = MagicMock(side_effect=AssertionError("startup side effect"))
    monkeypatch.setattr(bootstrap.bot, "get_me", side_effect_guard)
    monkeypatch.setattr(bootstrap.threading, "Thread", side_effect_guard)
    monkeypatch.setattr(bootstrap, "get_last_commit_info", side_effect_guard)

    result = bootstrap.preflight_compatibility()
    assert result == "4.0.0"
    assert order == ["deps", "sql", "version"]
    side_effect_guard.assert_not_called()


def test_preflight_incompatible_exits_without_startup_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stored version below MIN_VERSION exits 1 with no Telegram/thread/Git/write."""
    from teleboss.shared import bootstrap

    monkeypatch.setattr(bootstrap, "check_dependency_versions", lambda: None)
    monkeypatch.setattr(bootstrap.data, "sql_worker_get", lambda: None)
    monkeypatch.setattr(bootstrap.data, "MIN_VERSION", "4.0")
    monkeypatch.setattr(bootstrap.data, "VERSION", "4.0.0")

    writes: list[object] = []

    def _params(key: str, default_return=None, rewrite_value=None):  # noqa: ANN001
        if rewrite_value is not None:
            writes.append(rewrite_value)
            raise AssertionError("version must not be written during preflight")
        return _INCOMPATIBLE_VERSION

    monkeypatch.setattr(bootstrap.sqlWorker, "params", _params)

    side_effect_guard = MagicMock(side_effect=AssertionError("startup side effect"))
    monkeypatch.setattr(bootstrap.bot, "get_me", side_effect_guard)
    monkeypatch.setattr(bootstrap.threading, "Thread", side_effect_guard)
    monkeypatch.setattr(bootstrap, "get_last_commit_info", side_effect_guard)
    monkeypatch.setattr(bootstrap.bot, "send_message", side_effect_guard)

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.preflight_compatibility()
    assert exc_info.value.code == 1
    assert writes == []
    side_effect_guard.assert_not_called()


def test_preflight_dependency_exit_skips_sql_and_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dependency SystemExit must not reach SQL hydrate or version read."""
    from teleboss.shared import bootstrap

    later: list[str] = []

    def _deps() -> None:
        raise SystemExit(1)

    def _hydrate() -> None:
        later.append("sql")

    def _params(key: str, default_return=None, rewrite_value=None):  # noqa: ANN001
        later.append("version")
        return "4.0.0"

    monkeypatch.setattr(bootstrap, "check_dependency_versions", _deps)
    monkeypatch.setattr(bootstrap.data, "sql_worker_get", _hydrate)
    monkeypatch.setattr(bootstrap.sqlWorker, "params", _params)

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.preflight_compatibility()
    assert exc_info.value.code == 1
    assert later == []


def test_preflight_sql_failure_skips_version_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQL/config hydrate failure must not reach the stored-version reader."""
    from teleboss.shared import bootstrap

    later: list[str] = []

    def _hydrate() -> None:
        raise RuntimeError("sql unavailable")

    def _params(key: str, default_return=None, rewrite_value=None):  # noqa: ANN001
        later.append("version")
        return "4.0.0"

    monkeypatch.setattr(bootstrap, "check_dependency_versions", lambda: None)
    monkeypatch.setattr(bootstrap.data, "sql_worker_get", _hydrate)
    monkeypatch.setattr(bootstrap.sqlWorker, "params", _params)

    with pytest.raises(RuntimeError, match="sql unavailable"):
        bootstrap.preflight_compatibility()
    assert later == []


def test_preflight_equal_min_version_is_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stored version equal to MIN_VERSION is accepted and returned."""
    from teleboss.shared import bootstrap

    monkeypatch.setattr(bootstrap, "check_dependency_versions", lambda: None)
    monkeypatch.setattr(bootstrap.data, "sql_worker_get", lambda: None)
    monkeypatch.setattr(bootstrap.data, "MIN_VERSION", "4.0")
    monkeypatch.setattr(bootstrap.data, "VERSION", "4.0.0")
    monkeypatch.setattr(
        bootstrap.sqlWorker,
        "params",
        lambda key, default_return=None, rewrite_value=None: "4.0",
    )

    assert bootstrap.preflight_compatibility() == "4.0"


def test_init_consumes_snapshot_without_min_version_reread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``init(stored_version)`` uses the snapshot and does not re-run preflight gates."""
    from teleboss.shared import bootstrap

    def _fail_preflight_piece(*_a, **_k):  # noqa: ANN001
        raise AssertionError("preflight work must not re-run inside init")

    monkeypatch.setattr(bootstrap, "check_dependency_versions", _fail_preflight_piece)
    monkeypatch.setattr(bootstrap.data, "sql_worker_get", _fail_preflight_piece)
    monkeypatch.setattr(bootstrap.data, "MIN_VERSION", "4.0")
    monkeypatch.setattr(bootstrap.data, "VERSION", "4.0.0")
    monkeypatch.setattr(bootstrap.data, "main_chat_id", -1)
    monkeypatch.setattr(bootstrap.data, "CODENAME", "test")
    monkeypatch.setattr(bootstrap.data, "BUILD_DATE", "05.08.2026")

    me = MagicMock()
    me.id = 42
    monkeypatch.setattr(bootstrap.bot, "get_me", lambda: me)
    monkeypatch.setattr(bootstrap.threading, "Thread", MagicMock())
    monkeypatch.setattr(
        bootstrap,
        "get_last_commit_info",
        MagicMock(side_effect=FileNotFoundError("Folder .git not found")),
    )

    rewritten: list[str] = []

    def _params(key: str, default_return=None, rewrite_value=None):  # noqa: ANN001
        if rewrite_value is not None:
            rewritten.append(str(rewrite_value))
            return rewrite_value
        raise AssertionError("init must not re-read version from SQL")

    monkeypatch.setattr(bootstrap.sqlWorker, "params", _params)

    bootstrap.init("4.0.0")
    assert bootstrap.data.bot_id == 42
    assert rewritten == ["4.0.0"]


def _read_stored_version(db_path: Path) -> str:
    """Return the ``version`` key from the SQLite params blob."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT params FROM params").fetchone()
    assert row is not None
    return json.loads(row[0])["version"]


def test_poison_plugin_not_imported_on_incompatible_version() -> None:
    """Subprocess: incompatible stored version exits before poison import/ctor."""
    token = uuid.uuid4().hex[:10]
    work_name = f"_t04_preflight_{token}"
    workdir = REPO_ROOT / work_name
    plugins_dir = REPO_ROOT / f"{work_name}_plugins"
    import_sentinel = workdir / "poison_import.sentinel"
    ctor_sentinel = workdir / "poison_ctor.sentinel"
    db_path = workdir / "database.db"

    try:
        workdir.mkdir(parents=True, exist_ok=False)
        plugins_dir.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(_SMOKE_TEMPLATE, workdir / "config.ini")

        from teleboss.shared.config import ConfigData
        from teleboss.shared.storage.sql_worker import SqlWorker

        seed = dict(ConfigData.SQL_INIT)
        seed["version"] = _INCOMPATIBLE_VERSION
        SqlWorker(str(db_path), seed)
        assert _read_stored_version(db_path) == _INCOMPATIBLE_VERSION

        (plugins_dir / "__init__.py").write_text("", encoding="utf-8")
        poison_src = (
            "from pathlib import Path\n"
            f"_WORKDIR = Path(r'''{workdir}''')\n"
            "(_WORKDIR / 'poison_import.sentinel').write_text('imported', encoding='utf-8')\n"
            "\n"
            "class Plugin:\n"
            "    def __init__(self, built_in_commands_clear_dict):\n"
            "        (_WORKDIR / 'poison_ctor.sentinel').write_text('constructed', encoding='utf-8')\n"
            "        self.meta_info = {\n"
            "            'name': 'poison',\n"
            "            'type': 'simple',\n"
            "            'version-min': '0.0',\n"
            "            'version-target': '99.0',\n"
            "            'description': 'poison',\n"
            "        }\n"
            "        self.plugin_commands_dict = {}\n"
        )
        (plugins_dir / "poison.py").write_text(poison_src, encoding="utf-8")

        proc = subprocess.run(
            [str(_VENV_PYTHON), str(REPO_ROOT / "main.py"), work_name],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert proc.returncode == 1, (
            f"expected exit 1, got {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
        assert not import_sentinel.exists(), "poison module was imported"
        assert not ctor_sentinel.exists(), "poison Plugin constructor ran"
        assert _read_stored_version(db_path) == _INCOMPATIBLE_VERSION
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(plugins_dir, ignore_errors=True)
