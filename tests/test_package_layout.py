"""Standard ``src/teleboss/`` layout guards.

Physical package tree lives under ``src/teleboss/``; imports remain ``teleboss.*``.
No root ``teleboss/`` namespace-anchor package and no flat ``src/{app,...}``.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

from helpers import REPO_ROOT, assert_soft_version_order

_SRC_DOMAINS = ("app", "domain", "shared", "voting", "plugin_loader")

_IMPORT_FILE_CASES = (
    ("teleboss.app", "src/teleboss/app/__init__.py"),
    ("teleboss.domain", "src/teleboss/domain/__init__.py"),
    ("teleboss.shared", "src/teleboss/shared/__init__.py"),
    ("teleboss.voting", "src/teleboss/voting/__init__.py"),
    ("teleboss.plugin_loader", "src/teleboss/plugin_loader/__init__.py"),
    ("teleboss.shared.config", "src/teleboss/shared/config.py"),
)


def _load_pyproject() -> dict:
    path = REPO_ROOT / "pyproject.toml"
    assert path.is_file(), "pyproject.toml missing"
    with path.open("rb") as fh:
        return tomllib.load(fh)


def test_src_teleboss_domains_exist() -> None:
    """Assert product code lives under ``src/teleboss/{app,domain,...}``."""
    pkg = REPO_ROOT / "src" / "teleboss"
    assert pkg.is_dir()
    assert (pkg / "__init__.py").is_file()
    for name in _SRC_DOMAINS:
        domain = pkg / name
        assert domain.is_dir(), name
        assert (domain / "__init__.py").is_file(), name


def test_no_root_teleboss_package() -> None:
    """Forbid root ``teleboss/`` package tree (layout lives under ``src/``)."""
    assert not (REPO_ROOT / "teleboss").exists(), "root teleboss/ must not exist"


def test_no_flat_src_domain_trees() -> None:
    """Forbid leftover flat ``src/{app,domain,...}`` siblings of ``teleboss``."""
    src = REPO_ROOT / "src"
    # Ignore local packaging leftovers (gitignored ``*.egg-info``).
    children = sorted(
        p.name
        for p in src.iterdir()
        if p.is_dir() and not p.name.endswith(".egg-info")
    )
    assert children == ["teleboss"], children
    for name in _SRC_DOMAINS:
        assert not (src / name).exists(), f"flat src/{name} must not exist"


def test_pyproject_src_layout() -> None:
    """``package-dir`` maps ``""`` → ``src``; packages discovered under ``src``."""
    data = _load_pyproject()
    setuptools = data.get("tool", {}).get("setuptools", {})
    package_dir = setuptools.get("package-dir", {})
    assert package_dir == {"": "src"}, package_dir
    find = setuptools.get("packages", {}).get("find", {})
    assert find.get("where") == ["src"], find
    project = data["project"]
    assert project["name"] == "teleboss"
    config = importlib.import_module("teleboss.shared.config")
    assert project["version"] == config.ConfigData.VERSION
    scripts = project.get("scripts", {})
    assert scripts.get("teleboss") == "teleboss.app.entry:main"


def test_teleboss_imports_resolve_under_src(teleboss_runtime) -> None:
    """Editable/install mapping: ``import teleboss.*`` loads files under ``src/teleboss/``."""
    _ = teleboss_runtime  # fixture ensures package is importable
    for mod_name, rel_path in _IMPORT_FILE_CASES:
        mod = importlib.import_module(mod_name)
        mod_file = Path(mod.__file__).resolve()
        expected = (REPO_ROOT / rel_path).resolve()
        assert mod_file == expected, (mod_name, mod_file, expected)
        rel = mod_file.relative_to(REPO_ROOT)
        assert rel.parts[:2] == ("src", "teleboss"), rel


def test_configdata_version_soft_order_after_layout_move(teleboss_runtime) -> None:
    """Layout packaging keeps ConfigData soft version order (no durable hard pin)."""
    _ = teleboss_runtime
    config = importlib.import_module("teleboss.shared.config")
    assert_soft_version_order(config.ConfigData.MIN_VERSION, config.ConfigData.VERSION)
    cfg_path = Path(config.__file__).resolve()
    assert cfg_path == (REPO_ROOT / "src/teleboss/shared/config.py").resolve()
