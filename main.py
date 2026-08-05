"""Thin process shim: Python floor then delegate to ``teleboss.app.entry``."""

from teleboss.shared.python_floor import ensure_min_python

ensure_min_python()

from teleboss.app.entry import main

if __name__ == "__main__":
    main()
