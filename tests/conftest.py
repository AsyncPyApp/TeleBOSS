"""Session fixtures for offline TeleBOSS pytest runs.

No product imports at module top-level — ConfigData / TeleBot must see
sys.argv[1] workdir only after the smoke config is seeded.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from helpers import assert_soft_version_order

# Re-export for older imports / convenience.
__all__ = ["assert_soft_version_order"]

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_SMOKE_TEMPLATE = _FIXTURES_DIR / "smoke_config.ini.template"


@pytest.fixture(scope="session")
def smoke_workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session temp workdir with config.ini copied from the smoke template."""
    workdir = tmp_path_factory.mktemp("teleboss_smoke")
    dest = workdir / "config.ini"
    shutil.copyfile(_SMOKE_TEMPLATE, dest)
    return workdir


@pytest.fixture(scope="session", autouse=True)
def _seed_argv_before_runtime(smoke_workdir: Path) -> None:
    """Set sys.argv before any runtime / ConfigData import path."""
    sys.argv = ["pytest", str(smoke_workdir)]


@pytest.fixture(scope="session")
def teleboss_runtime(_seed_argv_before_runtime):  # noqa: ANN001 — lazy product import
    """Import runtime once after argv+seed; exposes the process TeleBot singleton."""
    import teleboss.shared.runtime as runtime

    return runtime


@pytest.fixture(scope="session")
def runtime_bot(teleboss_runtime):  # noqa: ANN001
    return teleboss_runtime.bot


@pytest.fixture(scope="session")
def runtime_data(teleboss_runtime):  # noqa: ANN001
    return teleboss_runtime.data


@pytest.fixture(scope="session", autouse=True)
def poll_engine_snapshot(teleboss_runtime):  # noqa: ANN001
    """Capture post_vote_list emptiness before any registry/plugin init in the suite."""
    from teleboss.voting.engine import PollEngine

    return {
        "PollEngine": PollEngine,
        "id": id(PollEngine.post_vote_list),
        "was_empty": len(PollEngine.post_vote_list) == 0,
    }
