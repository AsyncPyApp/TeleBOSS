"""ConfigData ↔ CHANGELOG / pyproject / README sync without pinning a release number.

Release tasks own the conscious VERSION bump and release-commit body checks.
This module asserts that the *current* ConfigData fields match the newest
changelog section, packaging metadata, and README badge, and that MIN_VERSION
remains a valid soft-upgrade floor.
"""

from __future__ import annotations

import re
import tomllib

from helpers import REPO_ROOT, assert_soft_version_order

_CHANGELOG = REPO_ROOT / "CHANGELOG.md"
_PYPROJECT = REPO_ROOT / "pyproject.toml"
_README = REPO_ROOT / "README.md"
_SECTION_RE = re.compile(
    r"^##\s+(?P<version>\d+\.\d+(?:\.\d+)?)\s+[—–-]\s+(?P<date>\d{2}\.\d{2}\.\d{4})\s*$",
    re.MULTILINE,
)
_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_BADGE_RE = re.compile(
    r"img\.shields\.io/badge/version-(?P<version>\d+\.\d+(?:\.\d+)?)-",
)
_BULLET_RE = re.compile(r"^\d+\.\s+\S", re.MULTILINE)


def _newest_changelog_section(text: str) -> tuple[str, str, str]:
    """Return ``(version, DD.MM.YYYY, section_body)`` for the newest release."""
    match = _SECTION_RE.search(text)
    assert match is not None, "CHANGELOG.md must contain a ## X.Y.Z — DD.MM.YYYY section"
    start = match.end()
    next_match = _SECTION_RE.search(text, start)
    end = next_match.start() if next_match is not None else len(text)
    body = text[start:end]
    return match.group("version"), match.group("date"), body


def test_configdata_matches_newest_changelog_section(runtime_data) -> None:
    """Newest CHANGELOG version/date must equal ConfigData.VERSION / BUILD_DATE."""
    changelog = _CHANGELOG.read_text(encoding="utf-8")
    newest_version, newest_date, _body = _newest_changelog_section(changelog)

    assert runtime_data.VERSION == newest_version
    assert runtime_data.BUILD_DATE == newest_date
    assert _DATE_RE.match(runtime_data.BUILD_DATE)


def test_newest_changelog_section_has_numbered_bullets() -> None:
    """Newest CHANGELOG section must list at least one numbered release bullet."""
    changelog = _CHANGELOG.read_text(encoding="utf-8")
    _version, _date, body = _newest_changelog_section(changelog)
    bullets = _BULLET_RE.findall(body)
    assert len(bullets) >= 1, "newest CHANGELOG section must have numbered bullets"


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


def test_pyproject_version_matches_configdata(runtime_data) -> None:
    """``[project].version`` in pyproject.toml must equal ConfigData.VERSION."""
    assert _PYPROJECT.is_file()
    with _PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    assert data["project"]["version"] == runtime_data.VERSION


def test_readme_badge_matches_configdata(runtime_data) -> None:
    """README version badge must show the same SemVer as ConfigData.VERSION."""
    assert _README.is_file()
    text = _README.read_text(encoding="utf-8")
    match = _BADGE_RE.search(text)
    assert match is not None, "README.md must contain a version-X.Y.Z shields badge"
    assert match.group("version") == runtime_data.VERSION
