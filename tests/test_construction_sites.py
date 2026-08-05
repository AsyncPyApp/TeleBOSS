"""Construction-site and post_vote_list assignment invariants."""

from __future__ import annotations

import re
from pathlib import Path

from helpers import REPO_ROOT

_SKIP_PARTS = {"__pycache__", ".git", ".venv", "venv", "node_modules", ".pytest_cache"}


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for p in REPO_ROOT.rglob("*.py"):
        if any(part in _SKIP_PARTS for part in p.parts):
            continue
        if p.name.startswith("_t0"):
            continue
        files.append(p)
    return files


def test_singleton_construction_sites_only_in_runtime() -> None:
    hits: list[str] = []
    for p in (REPO_ROOT / "teleboss").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if re.search(r"\b(ConfigData|Helper|SqlWorker|TeleBot)\(", s) and not s.startswith(
                "def "
            ):
                hits.append(f"{p.as_posix()}:{i}:{s}")
    only_runtime = all(
        "teleboss/shared/runtime.py" in h.replace("\\", "/") for h in hits
    )
    assert only_runtime and len(hits) == 4, f"hits={hits}"


def test_exactly_one_poll_engine_construction() -> None:
    ctor_hits: list[str] = []
    for p in _iter_py_files():
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if re.search(r"\bPollEngine\s*\(", s):
                ctor_hits.append(f"{p.as_posix()}:{i}:{s}")
    assert len(ctor_hits) == 1, f"hits={ctor_hits}"
    assert "teleboss/voting/engine.py" in ctor_hits[0].replace("\\", "/")


def test_no_post_vote_list_reassignment() -> None:
    assign_hits: list[str] = []
    engine_path = REPO_ROOT / "teleboss/voting/engine.py"
    text = engine_path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"\bpost_vote_list\s*=", line):
            assign_hits.append(f"{engine_path.as_posix()}:{i}:{line.strip()}")
    for p in list(REPO_ROOT.glob("*.py")) + list((REPO_ROOT / "teleboss").rglob("*.py")):
        if p.name.startswith("_t0"):
            continue
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"PollEngine\.post_vote_list\s*=", line) or re.search(
                r"poll_engine\.post_vote_list\s*=", line
            ):
                assign_hits.append(f"{p.as_posix()}:{i}:{line.strip()}")
    # Dedupe while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for h in assign_hits:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    assert len(unique) == 1, f"hits={unique}"
    assert "teleboss/voting/engine.py" in unique[0].replace("\\", "/")
    assert "post_vote_list = {}" in unique[0]
