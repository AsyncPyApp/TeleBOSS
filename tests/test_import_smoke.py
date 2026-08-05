"""Import smoke for teleboss entrypoints and thin main (no root shims)."""

from __future__ import annotations

import importlib

from helpers import REPO_ROOT, SHIM_MODS, module_imports


def test_import_teleboss_entrypoints_and_main(teleboss_runtime) -> None:
    for mod_name in (
        "main",
        "teleboss.shared.runtime",
        "teleboss.voting.engine",
        "teleboss.plugin_loader.loader",
        "teleboss.shared.storage.sql_worker",
        "teleboss.domain.postvote_registry",
        "teleboss.domain.moderation.prevote",
    ):
        importlib.import_module(mod_name)


def test_main_imports_only_teleboss_product() -> None:
    roots = {m.split(".")[0] for m in module_imports(REPO_ROOT / "main.py")}
    assert roots.isdisjoint(SHIM_MODS)
    assert "teleboss" in roots
    assert (REPO_ROOT / "teleboss/shared/python_floor.py").is_file()


def test_main_calls_python_floor_before_product_imports() -> None:
    main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    floor_import = main_src.find("from teleboss.shared.python_floor import ensure_min_python")
    floor_call = main_src.find("ensure_min_python()")
    first_app = main_src.find("from teleboss.app.")
    assert 0 <= floor_import < floor_call < first_app
