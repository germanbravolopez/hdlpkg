"""Enable ``python -m hdlpkg`` as an alias for the ``hdlpkg`` CLI."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
