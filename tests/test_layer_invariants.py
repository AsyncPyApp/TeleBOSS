"""Layer DAG, empty package inits, no root-shim imports under product ``src/``."""

from __future__ import annotations

import ast
import re

from helpers import REPO_ROOT, SHIM_MODS, module_imports

SHIM_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(" + "|".join(SHIM_MODS) + r")\b",
    re.MULTILINE,
)

_SRC = REPO_ROOT / "src"


def test_no_root_shim_imports_under_teleboss() -> None:
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in SHIM_IMPORT_RE.finditer(text):
            line = text[: m.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}:{m.group(0).strip()}")
    assert not offenders, offenders


def test_empty_package_inits() -> None:
    for rel in (
        "teleboss/__init__.py",
        "src/shared/__init__.py",
        "src/voting/__init__.py",
        "src/plugin_loader/__init__.py",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8").strip()
        assert text == "", f"{rel} not empty: {text!r}"


def test_shared_does_not_import_upper_layers() -> None:
    layer_re = re.compile(
        r"(teleboss\.(voting|domain|app|plugin_loader)|"
        r"^\s*(import|from)\s+(voting|domain|app|plugin_loader)\b)",
        re.M,
    )
    bad: list[str] = []
    for path in (_SRC / "shared").rglob("*.py"):
        if layer_re.search(path.read_text(encoding="utf-8")):
            bad.append(str(path.relative_to(REPO_ROOT)))
    assert not bad, bad


def test_voting_layer_rules() -> None:
    layer_re = re.compile(
        r"(teleboss\.(domain|app|plugin_loader)|"
        r"^\s*(import|from)\s+(domain|app|plugin_loader)\b)",
        re.M,
    )
    bad_layers: list[str] = []
    utils_imports: list[str] = []
    for path in (_SRC / "voting").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if layer_re.search(text):
            bad_layers.append(str(path.relative_to(REPO_ROOT)))
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"^\s*(from|import)\s+utils\b", line):
                utils_imports.append(f"{path.as_posix()}:{i}:{line.strip()}")
        for mod in module_imports(path):
            assert not (mod.startswith("teleboss.domain") or mod == "teleboss.domain"), (
                f"{path.name} imports {mod}"
            )
    assert not bad_layers, bad_layers
    assert not utils_imports, utils_imports


def test_plugin_loader_layer_shared_and_voting_only() -> None:
    loader_src = (_SRC / "plugin_loader/loader.py").read_text(encoding="utf-8")
    tree = ast.parse(loader_src)
    forbidden_prefixes = (
        "teleboss.domain",
        "teleboss.app",
        "utils",
        "poll_engines",
        "plugin_engine",
        "prevote",
        "postvote",
        "main",
    )
    bad_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            if any(mod == p or mod.startswith(p + ".") for p in forbidden_prefixes):
                bad_imports.append(mod)
            if mod.startswith("teleboss.") and not (
                mod.startswith("teleboss.shared") or mod.startswith("teleboss.voting")
            ):
                bad_imports.append(mod)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes):
                    bad_imports.append(name)
    assert not bad_imports, bad_imports


def test_no_domain_cross_imports_postvote() -> None:
    sibling_domains = {"moderation", "settings", "admin", "allies", "content"}
    cross: list[tuple[str, str]] = []
    for domain in sibling_domains:
        path = _SRC / "domain" / domain / "postvote.py"
        for mod in module_imports(path):
            if not mod.startswith("teleboss.domain."):
                continue
            parts = mod.split(".")
            if len(parts) >= 3 and parts[2] in sibling_domains and parts[2] != domain:
                cross.append((domain, mod))
    assert not cross, cross


def test_no_domain_cross_imports_prevote() -> None:
    sibling_domains = {"moderation", "settings", "admin", "allies", "content"}
    for domain in sibling_domains:
        domain_dir = _SRC / "domain" / domain
        prevote_files = sorted(domain_dir.glob("prevote*.py"))
        assert prevote_files, f"no prevote*.py under {domain}"
        for path in prevote_files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            is_barrel = path.name == "prevote.py"
            for node in ast.walk(tree):
                # Absolute teleboss.* only — relative imports bypass the domain prefix check.
                if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
                    raise AssertionError(f"{rel} relative import level={node.level} module={node.module!r}")
                mods: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods.append(node.module)
                elif isinstance(node, ast.Import):
                    mods.extend(alias.name for alias in node.names)
                for mod in mods:
                    if not mod.startswith("teleboss."):
                        continue
                    if mod.startswith("teleboss.shared.") or mod.startswith("teleboss.voting."):
                        continue
                    if mod.startswith("teleboss.domain."):
                        parts = mod.split(".")
                        same_domain = len(parts) >= 3 and parts[2] == domain
                        # Thin barrels may re-export same-domain sibling modules only.
                        if is_barrel and same_domain:
                            continue
                        raise AssertionError(f"{rel} forbidden domain import {mod}")
                    raise AssertionError(f"{rel} bad layer import {mod}")


def test_no_top_level_plugins_package() -> None:
    plugins = REPO_ROOT / "plugins"
    assert not plugins.is_dir() or not (plugins / "__init__.py").exists()
