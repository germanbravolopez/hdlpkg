"""Text-preserving edits to an existing ``ip.toml`` (behind ``hdlpkg add``).

``tomllib`` is read-only and the project keeps zero third-party runtime deps, so to
add or update a dependency without clobbering the author's formatting and comments
we do a careful, line-based edit of the ``[dependencies]`` table rather than
re-rendering the whole manifest. This module is **pure**: it takes and returns TOML
text; the CLI re-parses the result with :class:`~hdl_ip_packager.manifest.Manifest`
to guarantee the edit produced a still-valid manifest before writing it.

The dependency key is the quoted ``"vendor:library:name"`` form the manifest already
uses (the colons require quoting). Existing keys are matched on that canonical
double-quoted form.
"""

from __future__ import annotations

from .version import VersionConstraint
from .vlnv import PackageRef

__all__ = ["add_dependency"]


def add_dependency(text: str, ref: PackageRef, constraint: VersionConstraint) -> str:
    """Return *text* with ``ref = constraint`` inserted into (or updated in)
    ``[dependencies]``.

    If the package is already a dependency, its constraint line is replaced. If the
    ``[dependencies]`` table is absent, one is appended. Output always ends with a
    trailing newline.
    """
    key = f'"{ref}"'
    new_line = f'{key} = "{constraint}"'
    lines = text.splitlines()

    start = next((i for i, ln in enumerate(lines) if ln.strip() == "[dependencies]"), None)
    if start is None:
        body = "\n".join(lines)
        prefix = body + "\n" if body and not body.endswith("\n") else body
        return f"{prefix}\n[dependencies]\n{new_line}\n"

    # The table runs until the next ``[...]`` header (or end of file).
    end = next(
        (j for j in range(start + 1, len(lines)) if lines[j].lstrip().startswith("[")),
        len(lines),
    )

    for k in range(start + 1, end):
        if lines[k].strip().startswith(key):  # same package already declared
            lines[k] = new_line
            return "\n".join(lines) + "\n"

    # Insert after the last non-blank line of the table, before any trailing blanks.
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, new_line)
    return "\n".join(lines) + "\n"
