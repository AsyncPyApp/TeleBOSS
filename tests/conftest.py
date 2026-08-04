"""Session fixtures for offline TeleBOSS pytest runs.

No product imports at module top-level — ConfigData / TeleBot must see
sys.argv[1] workdir only after the smoke config is seeded.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from packaging.version import parse as parse_version

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_SMOKE_TEMPLATE = _FIXTURES_DIR / "smoke_config.ini.template"


def assert_soft_version_order(min_version: str, version: str) -> None:
    """Soft VERSION gate: MIN_VERSION <= VERSION via packaging.version."""
    assert isinstance(min_version, str) and min_version.strip()
    assert isinstance(version, str) and version.strip()
    assert parse_version(min_version) <= parse_version(version)


@pytest.fixture(scope="session")
def smoke_workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session temp workdir with config.ini copied from the smoke template."""
    workdir = tmp_path_factory.mktemp("teleboss_smoke")
    dest = workdir / "config.ini"
    shutil.copyfile(_SMOKE_TEMPLATE, dest)
    return workdir


@pytest.fixture(scope="session", autouse=True)
def _seed_argv_before_runtime(smoke_workdir: Path) -> None:
    """Set sys.argv before any utils / runtime / ConfigData import path."""
    sys.argv = ["pytest", str(smoke_workdir)]


@pytest.fixture(scope="session")
def teleboss_runtime(_seed_argv_before_runtime):  # noqa: ANN001 — lazy product import
    """Import runtime once after argv+seed; exposes the process TeleBot singleton."""
    import teleboss.shared.runtime as runtime

    return runtime


@pytest.fixture(scope="session")
def utils_mod(teleboss_runtime):  # noqa: ANN001 — ensures runtime first
    """Import root utils shim after runtime (same TeleBot singleton)."""
    import utils

    return utils


@pytest.fixture(scope="session")
def runtime_bot(teleboss_runtime):  # noqa: ANN001
    return teleboss_runtime.bot


@pytest.fixture(scope="session")
def runtime_data(teleboss_runtime):  # noqa: ANN001
    return teleboss_runtime.data
