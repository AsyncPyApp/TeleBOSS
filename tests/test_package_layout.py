"""Physical flat ``src/`` layout + setuptools ``package-dir`` guards.

Plan ``20260805-src-package-elephants`` T03 / Security M1:
flat ``src/{app,domain,...}``, no ``src/teleboss/`` product tree, root
``teleboss/`` namespace anchor only, imports remain ``teleboss.*``.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

from helpers import REPO_ROOT

_SRC_DOMAINS = ("app", "domain", "shared", "voting", "plugin_loader")

_EXPECTED_PACKAGE_DIR = {
    "teleboss.app": "src/app",
    "teleboss.domain": "src/domain",
    "teleboss.shared": "src/shared",
    "teleboss.voting": "src/voting",
    "teleboss.plugin_loader": "src/plugin_loader",
}

# One importable module per mapped top-level package (resolves via package-dir).
_IMPORT_FILE_CASES = (
    ("teleboss.app", "src/app/__init__.py"),
    ("teleboss.domain", "src/domain/__init__.py"),
    ("teleboss.shared", "src/shared/__init__.py"),
    ("teleboss.voting", "src/voting/__init__.py"),
    ("teleboss.plugin_loader", "src/plugin_loader/__init__.py"),
    ("teleboss.shared.config", "src/shared/config.py"),
)


def _load_pyproject() -> dict:
    path = REPO_ROOT / "pyproject.toml"
    assert path.is_file(), "pyproject.toml missing"
    with path.open("rb") as fh:
        return tomllib.load(fh)


def test_flat_src_domains_exist() -> None:
    """Assert product code lives under flat ``src/{app,domain,...}``."""
    src = REPO_ROOT / "src"
    assert src.is_dir()
    for name in _SRC_DOMAINS:
        domain = src / name
        assert domain.is_dir(), name
        assert (domain / "__init__.py").is_file(), name


def test_no_src_teleboss_product_tree() -> None:
    """Forbid nested ``src/teleboss/`` product code (plan §4.1 / Security M1)."""
    nested = REPO_ROOT / "src" / "teleboss"
    assert not nested.exists(), "src/teleboss must not exist"


def test_root_teleboss_is_namespace_anchor_only() -> None:
    """Root ``teleboss/`` keeps only ``__init__.py`` — no duplicate code tree."""
    root_pkg = REPO_ROOT / "teleboss"
    assert root_pkg.is_dir()
    assert (root_pkg / "__init__.py").is_file()
    children = sorted(
        p.name
        for p in root_pkg.iterdir()
        if p.name != "__pycache__" and not p.name.endswith(".pyc")
    )
    assert children == ["__init__.py"], children
    for name in _SRC_DOMAINS:
        assert not (root_pkg / name).exists(), f"duplicate tree teleboss/{name}"


def test_pyproject_package_dir_maps_flat_src() -> None:
    """``[tool.setuptools.package-dir]`` maps ``teleboss.*`` onto flat ``src/``."""
    data = _load_pyproject()
    package_dir = data.get("tool", {}).get("setuptools", {}).get("package-dir", {})
    assert package_dir == _EXPECTED_PACKAGE_DIR, package_dir
    project = data["project"]
    assert project["name"] == "teleboss"
    assert project["version"] == "4.0.1"
    assert "scripts" not in project, "T03 must not add [project.scripts]"


def test_teleboss_imports_resolve_under_src(teleboss_runtime) -> None:
    """Editable/install mapping: ``import teleboss.*`` loads files under ``src/``."""
    _ = teleboss_runtime  # fixture ensures package is importable
    for mod_name, rel_path in _IMPORT_FILE_CASES:
        mod = importlib.import_module(mod_name)
        mod_file = Path(mod.__file__).resolve()
        expected = (REPO_ROOT / rel_path).resolve()
        assert mod_file == expected, (mod_name, mod_file, expected)
        rel = mod_file.relative_to(REPO_ROOT)
        assert rel.parts[0] == "src", rel


def test_configdata_version_unchanged_by_layout_move(teleboss_runtime) -> None:
    """T03 is packaging-only — ConfigData.VERSION stays on the prior release."""
    _ = teleboss_runtime
    config = importlib.import_module("teleboss.shared.config")
    assert config.ConfigData.VERSION == "4.0.1"
    cfg_path = Path(config.__file__).resolve()
    assert cfg_path == (REPO_ROOT / "src/shared/config.py").resolve()
