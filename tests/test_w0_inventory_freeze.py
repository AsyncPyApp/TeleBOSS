"""W0 inventory freeze: root shims, product callers, META notes, soft VERSION."""

from __future__ import annotations

import re

from helpers import (
    PRODUCT_SHIM_CALLER_FILES,
    REPO_ROOT,
    SHIM_CANONICAL_NOTES,
    SHIM_MODS,
    assert_soft_version_order,
    module_imports,
)

# Skip inventory noise and non-product trees when scanning shim callers.
_SKIP_DIR_PARTS = frozenset(
    {".venv", "tests", ".cursor", "__pycache__", ".git", ".pytest_cache"}
)
_SHIM_SET = frozenset(SHIM_MODS)
SHIM_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(" + "|".join(SHIM_MODS) + r")\b",
    re.MULTILINE,
)


def _product_shim_caller_files() -> set[str]:
    """Return relative paths of product modules that import root shims.

    Excludes venv/tests/plans/cache, and the six root shim files themselves.
    Paths use POSIX separators (e.g. ``main.py``).
    """
    callers: set[str] = set()
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        if any(part in _SKIP_DIR_PARTS for part in rel.parts):
            continue
        if len(rel.parts) == 1 and rel.stem in _SHIM_SET:
            continue
        mods = module_imports(path)
        if any(m.split(".")[0] in _SHIM_SET for m in mods):
            callers.add(rel.as_posix())
    return callers


def test_six_root_shim_files_exist() -> None:
    assert len(SHIM_MODS) == 6
    for name in SHIM_MODS:
        path = REPO_ROOT / f"{name}.py"
        assert path.is_file(), f"missing root shim {path.name}"


def test_shim_canonical_notes_cover_shim_mods() -> None:
    assert set(SHIM_CANONICAL_NOTES) == set(SHIM_MODS)
    assert len(SHIM_MODS) == 6
    for name, note in SHIM_CANONICAL_NOTES.items():
        assert isinstance(note, str) and note.strip(), name


def test_product_shim_callers_match_w0_golden() -> None:
    """W0 pre-migrate: only main.py among product files imports root shims."""
    assert _product_shim_caller_files() == set(PRODUCT_SHIM_CALLER_FILES)
    assert PRODUCT_SHIM_CALLER_FILES == frozenset({"main.py"})


def test_teleboss_has_zero_root_shim_imports() -> None:
    offenders: list[str] = []
    for path in (REPO_ROOT / "teleboss").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in SHIM_IMPORT_RE.finditer(text):
            line = text[: m.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}:{m.group(0).strip()}")
    assert not offenders, offenders


def test_soft_version_fields_present(runtime_data) -> None:
    assert_soft_version_order(runtime_data.MIN_VERSION, runtime_data.VERSION)
    assert isinstance(runtime_data.BUILD_DATE, str) and runtime_data.BUILD_DATE.strip()
    assert isinstance(runtime_data.CODENAME, str) and runtime_data.CODENAME.strip()
