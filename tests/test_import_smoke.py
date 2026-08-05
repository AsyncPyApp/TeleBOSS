"""Import smoke for root shims and main (deduped from _t03–_t09)."""

from __future__ import annotations

import ast

from helpers import REPO_ROOT


def test_import_root_shims_and_main(utils_mod) -> None:
    for mod_name in ("main", "prevote", "postvote", "poll_engines", "plugin_engine", "sql_worker"):
        __import__(mod_name)


def test_consumer_utils_symbols_on_shim(utils_mod) -> None:
    needed: set[str] = set()
    for fname in ("main.py", "prevote.py", "postvote.py", "poll_engines.py", "plugin_engine.py"):
        tree = ast.parse((REPO_ROOT / fname).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "utils"
            ):
                needed.add(node.attr)
            if isinstance(node, ast.ImportFrom) and node.module == "utils":
                for alias in node.names:
                    needed.add(alias.name)

    shim: set[str] = set()
    utree = ast.parse((REPO_ROOT / "utils.py").read_text(encoding="utf-8"))
    for node in utree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                shim.add(alias.asname or alias.name)

    missing = sorted(needed - shim)
    runtime_miss = sorted(n for n in needed if not hasattr(utils_mod, n))
    assert not missing, f"AST missing on shim: {missing}"
    assert not runtime_miss, f"runtime missing on shim: {runtime_miss}"


def test_poll_engines_shim_present_without_product_callers() -> None:
    """After main migrate, listed product files do not import poll_engines; shim stays until T05."""
    caller_from_shim: list[str] = []
    for fname in ("prevote.py", "postvote.py", "plugin_engine.py", "main.py"):
        tree = ast.parse((REPO_ROOT / fname).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "poll_engines" or node.module.startswith("poll_engines."):
                    caller_from_shim.append(fname)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "poll_engines" or alias.name.startswith("poll_engines."):
                        caller_from_shim.append(fname)
    assert not caller_from_shim, f"unexpected poll_engines callers: {caller_from_shim}"
    assert (REPO_ROOT / "poll_engines.py").is_file()


def test_postvote_shim_no_utils_or_poll_engines() -> None:
    from helpers import module_imports

    shim_mods = module_imports(REPO_ROOT / "postvote.py")
    assert "utils" not in shim_mods
    assert "poll_engines" not in shim_mods


def test_prevote_shim_no_wildcard_and_all_len() -> None:
    shim_src = (REPO_ROOT / "prevote.py").read_text(encoding="utf-8")
    assert "import *" not in shim_src
    shim_tree = ast.parse(shim_src)
    all_assign = None
    for node in shim_tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__":
                    all_assign = node.value
    assert isinstance(all_assign, ast.List)
    assert len(all_assign.elts) == 28
