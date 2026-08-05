"""Bootstrap / entry source-order gates (no polling execution)."""

from __future__ import annotations

import ast

from helpers import (
    MAIN_BOOTSTRAP_AST_CALLS,
    MAIN_BOOTSTRAP_ORDER,
    REPO_ROOT,
    main_bootstrap_ast_call_names,
    main_bootstrap_block_source,
)


def test_bootstrap_py_needles() -> None:
    boot = (REPO_ROOT / "src/shared/bootstrap.py").read_text(encoding="utf-8")
    assert "def preflight_compatibility()" in boot
    assert "data.MIN_VERSION" in boot
    assert "sys.exit(1)" in boot
    assert "for command_list in (plugins_command_list, built_in_command_list):" in boot
    assert "def init(stored_version" in boot
    assert 'distribution("teleboss")' in boot
    assert "os.path.isfile(file_name)" not in boot
    assert "open('requirements.txt'" not in boot


def test_main_bootstrap_order() -> None:
    boot_src = main_bootstrap_block_source()
    positions = [boot_src.find(n) for n in MAIN_BOOTSTRAP_ORDER]
    assert all(p >= 0 for p in positions), f"missing needles positions={positions}"
    assert positions == sorted(positions), f"order wrong positions={positions}"


def test_main_bootstrap_ast_call_order() -> None:
    """AST-aware exact order: post-votes → preflight → plugins → init → register → recovery."""
    names = main_bootstrap_ast_call_names()
    expected = list(MAIN_BOOTSTRAP_AST_CALLS)
    assert names == expected, f"AST call order wrong: {names} != {expected}"


def test_entry_handler_import_order() -> None:
    entry_src = (REPO_ROOT / "src/app/entry.py").read_text(encoding="utf-8")
    entry_tree = ast.parse(entry_src)
    import_names: list[str] = []
    for n in entry_tree.body:
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith(
            "teleboss.app.handlers"
        ):
            for alias in n.names:
                import_names.append(alias.name)
    assert import_names == ["membership", "captcha", "votes", "help"]


def test_main_is_thin_entry_delegate() -> None:
    """Root ``main.py`` must only floor-check and call ``entry.main``."""
    main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    assert "from teleboss.app.entry import main" in main_src
    assert "BuildInCommands" not in main_src
    assert "preflight_compatibility" not in main_src
    assert "bot." + "_".join(("infinity", "polling")) not in main_src
    assert "Plugins(" not in main_src


def test_main_does_not_import_shims() -> None:
    """After T02, main.py must not import any of the six root shim modules."""
    from helpers import SHIM_MODS, module_imports

    roots = {m.split(".")[0] for m in module_imports(REPO_ROOT / "main.py")}
    assert roots.isdisjoint(SHIM_MODS)


def test_membership_uses_prevote_new_user_checker() -> None:
    """Join-path still goes through prevote.NewUserChecker (may live in handler, not thin main)."""
    membership = (REPO_ROOT / "src/app/handlers/membership.py").read_text(encoding="utf-8")
    assert "NewUserChecker" in membership
    assert "prevote" in membership or "teleboss.domain" in membership


def test_post_vote_list_init_before_plugins() -> None:
    entry_src = (REPO_ROOT / "src/app/entry.py").read_text(encoding="utf-8")
    init_pos = entry_src.find("post_vote_list_init()")
    preflight_pos = entry_src.find("preflight_compatibility()")
    plugins_pos = entry_src.find("Plugins(")
    assert 0 <= init_pos < preflight_pos < plugins_pos
