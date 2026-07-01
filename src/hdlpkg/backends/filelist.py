"""Filelist backend: emit flat, ordered ``.f`` source lists, one per HDL type.

Unlike the tool-specific backends, this one drives no tool. It writes the resolved,
compile-ordered source paths (dependencies first, root last) as plain ``-f``-style
filelists -- one per HDL kind -- so a Makefile (or any flow without a dedicated hdlpkg
backend, e.g. QuestaSim or Quartus) can compile the IP straight from the cache without the
sources ever being vendored into the project tree. Each filelist is a newline-separated
list of absolute paths in the order the tool should read them.
"""

from __future__ import annotations

import re

from .base import Backend, GeneratedFiles
from .edam import EdaDesign

__all__ = ["FilelistBackend"]

# Clean filename stems for the known HDL kinds; anything else is slugified (below).
_TYPE_STEM = {"vhdl": "vhdl", "verilog": "verilog", "systemVerilog": "systemverilog"}


def _type_stem(file_type: str) -> str:
    """A filesystem-safe stem for *file_type* (so an unknown type still gets its own list)."""
    if file_type in _TYPE_STEM:
        return _TYPE_STEM[file_type]
    return re.sub(r"[^a-z0-9]+", "-", file_type.lower()).strip("-") or "other"


class FilelistBackend(Backend):
    """Generate one ordered ``<name>.<type>.f`` filelist per HDL type in the design."""

    name = "filelist"

    def generate(self, design: EdaDesign) -> GeneratedFiles:
        # Group paths by file type, preserving the design's compile order within each type.
        by_type: dict[str, list[str]] = {}
        for eda_file in design.files:
            by_type.setdefault(eda_file.file_type, []).append(eda_file.path)
        return {
            f"{design.name}.{_type_stem(file_type)}.f": "\n".join(paths) + "\n"
            for file_type, paths in by_type.items()
        }
