"""Bootstrap / main source-order gates (no polling execution)."""

from __future__ import annotations

import ast

from helpers import MAIN_BOOTSTRAP_ORDER, REPO_ROOT, main_bootstrap_block_source


def test_bootstrap_py_needles() -> None:
    boot = (REPO_ROOT / "teleboss/shared/bootstrap.py").read_text(encoding="utf-8")
    assert "data.MIN_VERSION" in boot
    assert "sys.exit(1)" in boot
    assert "for command_list in (plugins_command_list, built_in_command_list):" in boot


def test_main_bootstrap_order() -> None:
    boot_src = main_bootstrap_block_source()
    positions = [boot_src.find(n) for n in MAIN_BOOTSTRAP_ORDER]
    assert all(p >= 0 for p in positions), f"missing needles positions={positions}"
    assert positions == sorted(positions), f"order wrong positions={positions}"


def test_main_handler_import_order() -> None:
    main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    main_tree = ast.parse(main_src)
    import_names: list[str] = []
    for n in main_tree.body:
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith(
            "teleboss.app.handlers"
        ):
            for alias in n.names:
                import_names.append(alias.name)
    assert import_names == ["membership", "captcha", "votes", "help"]


def test_main_still_imports_shims() -> None:
    main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    assert "import utils" in main_src
    assert "import plugin_engine" in main_src
    assert "import postvote" in main_src


def test_membership_uses_prevote_new_user_checker() -> None:
    """Join-path still goes through prevote.NewUserChecker (may live in handler, not thin main)."""
    membership = (REPO_ROOT / "teleboss/app/handlers/membership.py").read_text(encoding="utf-8")
    assert "NewUserChecker" in membership
    assert "prevote" in membership or "teleboss.domain" in membership


def test_post_vote_list_init_before_plugins() -> None:
    main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    init_pos = main_src.find("postvote.post_vote_list_init()")
    plugins_pos = main_src.find("Plugins(")
    assert 0 <= init_pos < plugins_pos
