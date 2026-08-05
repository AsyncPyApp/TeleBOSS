"""ConfigData ↔ CHANGELOG consistency without pinning a future release number.

T06 owns the conscious PATCH bump (e.g. 4.0.1) and release-commit body checks.
This module only asserts that the *current* ConfigData fields match the newest
changelog section and that MIN_VERSION remains a valid soft-upgrade floor.
"""

from __future__ import annotations

import re

from helpers import REPO_ROOT, assert_soft_version_order

_CHANGELOG = REPO_ROOT / "CHANGELOG.md"
_SECTION_RE = re.compile(
    r"^##\s+(?P<version>\d+\.\d+(?:\.\d+)?)\s+[—–-]\s+(?P<date>\d{2}\.\d{2}\.\d{4})\s*$",
    re.MULTILINE,
)
_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


def _newest_changelog_section(text: str) -> tuple[str, str]:
    """Return ``(version, DD.MM.YYYY)`` for the first (newest) release section."""
    match = _SECTION_RE.search(text)
    assert match is not None, "CHANGELOG.md must contain a ## X.Y.Z — DD.MM.YYYY section"
    return match.group("version"), match.group("date")


def test_configdata_matches_newest_changelog_section(runtime_data) -> None:
    """Newest CHANGELOG version/date must equal ConfigData.VERSION / BUILD_DATE."""
    changelog = _CHANGELOG.read_text(encoding="utf-8")
    newest_version, newest_date = _newest_changelog_section(changelog)

    assert runtime_data.VERSION == newest_version
    assert runtime_data.BUILD_DATE == newest_date
    assert _DATE_RE.match(runtime_data.BUILD_DATE)


def test_min_version_is_valid_soft_floor(runtime_data) -> None:
    """MIN_VERSION is present, parseable, and <= VERSION (no future release pin)."""
    assert_soft_version_order(runtime_data.MIN_VERSION, runtime_data.VERSION)
    assert isinstance(runtime_data.CODENAME, str) and runtime_data.CODENAME.strip()


def test_changelog_exists_and_is_newest_first() -> None:
    """CHANGELOG.md exists; release sections keep newest-first SemVer order."""
    assert _CHANGELOG.is_file()
    text = _CHANGELOG.read_text(encoding="utf-8")
    sections = _SECTION_RE.findall(text)
    assert len(sections) >= 1
    # Soft newest-first: first section version must be the maximum by packaging order.
    from packaging.version import parse as parse_version

    versions = [parse_version(v) for v, _ in sections]
    assert versions[0] == max(versions)
