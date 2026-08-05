"""Editable-install / console-entry smoke (no polling)."""

from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
import textwrap

from helpers import REPO_ROOT

_VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
_VENV_TELEBOSS = REPO_ROOT / ".venv" / "Scripts" / "teleboss.exe"
_SMOKE_TEMPLATE = REPO_ROOT / "tests" / "fixtures" / "smoke_config.ini.template"


def test_entry_main_is_callable(teleboss_runtime) -> None:
    """``teleboss.app.entry:main`` is importable and callable after install."""
    _ = teleboss_runtime
    from teleboss.app.entry import main

    assert callable(main)


def test_console_script_entry_point_registered() -> None:
    """``[project.scripts] teleboss`` resolves to ``teleboss.app.entry:main``."""
    eps = importlib.metadata.entry_points(group="console_scripts")
    matches = [ep for ep in eps if ep.name == "teleboss"]
    assert matches, "console script teleboss not registered (pip install -e .?)"
    assert matches[0].value == "teleboss.app.entry:main"


def test_teleboss_console_script_exists_on_path() -> None:
    """Editable install exposes a ``teleboss`` launcher under the project venv."""
    assert _VENV_TELEBOSS.is_file() or shutil.which("teleboss") is not None


def test_entry_module_import_subprocess(tmp_path) -> None:  # noqa: ANN001
    """Subprocess import of entry with argv workdir; does not call ``main()``."""
    workdir = tmp_path / "entry_smoke_wd"
    workdir.mkdir()
    shutil.copyfile(_SMOKE_TEMPLATE, workdir / "config.ini")
    script = textwrap.dedent(
        f"""
        import sys
        sys.argv = ["entry-smoke", r"{workdir}"]
        from teleboss.app.entry import main
        import inspect
        assert callable(main)
        assert inspect.isfunction(main)
        """
    )
    proc = subprocess.run(
        [str(_VENV_PYTHON), "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
