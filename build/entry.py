"""PyInstaller entry point.

``mustacom/__main__.py`` uses package-relative imports, so it cannot be fed
directly to PyInstaller as a top-level script; this tiny launcher imports the
real ``main`` from the package (which PyInstaller collects in full).
"""

from mustacom.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
