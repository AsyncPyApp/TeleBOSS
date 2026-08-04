"""Bootstrap proof for the offline pytest harness (T01)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from conftest import assert_soft_version_order

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TESTS_DIR = Path(__file__).resolve().parent

# Telegram-like token shape used only to reject non-dummy secrets in suite sources.
_TOKEN_LIKE = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{15,}\b")
_DUMMY_TOKEN_MARKERS = ("SMOKE", "DUMMY", "TEST")


def _iter_suite_text_files() -> list[Path]:
    files: list[Path] = []
    files.extend(_TESTS_DIR.rglob("*.py"))
    files.extend((_TESTS_DIR / "fixtures").rglob("*"))
    return [p for p in files if p.is_file()]


def test_soft_version_order(runtime_data) -> None:
    assert_soft_version_order(runtime_data.MIN_VERSION, runtime_data.VERSION)
    assert runtime_data.BUILD_DATE and isinstance(runtime_data.BUILD_DATE, str)
    assert runtime_data.CODENAME and isinstance(runtime_data.CODENAME, str)


def test_utils_bot_is_runtime_bot(utils_mod, teleboss_runtime) -> None:
    assert utils_mod.bot is teleboss_runtime.bot
    assert utils_mod.data is teleboss_runtime.data


def test_chat_id_init_smoke_semantics(runtime_data) -> None:
    assert runtime_data.main_chat_id == -1
    assert runtime_data.debug is True


def test_no_top_level_plugins_package() -> None:
    assert not (_REPO_ROOT / "plugins" / "__init__.py").is_file()


def test_smoke_workdir_seeded_independently(smoke_workdir: Path) -> None:
    """Fixture-owned temp config — not coupled to root _smoke_wd."""
    config = smoke_workdir / "config.ini"
    assert config.is_file()
    text = config.read_text(encoding="utf-8")
    assert "0000000000:SMOKE_DUMMY_TOKEN_TEST" in text
    assert "chat-id = init" in text
    assert smoke_workdir.resolve() != (_REPO_ROOT / "_smoke_wd").resolve()
    assert "_smoke_wd" not in str(smoke_workdir.resolve())


def test_argv_points_at_fixture_workdir(smoke_workdir: Path) -> None:
    assert len(sys.argv) >= 2
    assert Path(sys.argv[1]).resolve() == smoke_workdir.resolve()


def test_requirements_dev_layout() -> None:
    product = (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    dev = (_REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "pytest" not in product.lower()
    assert "pytest>=8.3,<9" in dev.replace(" ", "")


def test_suite_hygiene_no_polling_pins_or_live_tokens() -> None:
    # Build needles at runtime so this file does not embed the banned phrases.
    forbidden_substrings = (
        "_".join(("infinity", "polling")),
        ".".join(("3", "3", "2")),
        " ".join(("git", "show")),
        "-".join(("HEAD", "diff")),
        "_".join(("git", "show")),
    )
    for path in _iter_suite_text_files():
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for needle in forbidden_substrings:
            assert needle.lower() not in lower, f"{path.name} contains forbidden {needle!r}"
        for match in _TOKEN_LIKE.finditer(text):
            token = match.group(0)
            assert any(m in token.upper() for m in _DUMMY_TOKEN_MARKERS), (
                f"{path.name} has non-dummy token-like string: {token!r}"
            )
