"""Fail-closed interpreter gate for TeleBOSS (stdlib only)."""

from __future__ import annotations

import sys

MIN_PYTHON = (3, 14, 6)


def ensure_min_python(
    version_info: tuple[int, ...] | None = None,
) -> None:
    """Exit with a clear message when the interpreter is below the floor.

    Args:
        version_info: Optional override for tests; defaults to ``sys.version_info``.
    """
    info = sys.version_info if version_info is None else version_info
    found = (int(info[0]), int(info[1]), int(info[2]))
    if found < MIN_PYTHON:
        required = ".".join(str(part) for part in MIN_PYTHON)
        print(
            f"TeleBOSS requires Python {required}+ "
            f"(found {found[0]}.{found[1]}.{found[2]}).",
            file=sys.stderr,
        )
        sys.exit(1)
