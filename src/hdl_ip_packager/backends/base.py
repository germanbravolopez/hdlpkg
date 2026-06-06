"""The tool-flow backend interface.

A *backend* turns the tool-agnostic :class:`~hdl_ip_packager.backends.edam.EdaDesign`
into the concrete input files one EDA tool consumes (a Verilator ``.vc`` command
file, a Vivado source ``.tcl`` script, ...). Backends are **pure**: ``generate``
returns a ``{filename: text}`` mapping and writes nothing; the CLI layer writes
those files to disk. Each backend is keyed by the manifest ``toolflow`` name.
"""

from __future__ import annotations

import abc

from .edam import EdaDesign

__all__ = ["Backend", "GeneratedFiles"]

# A backend's output: relative filename -> file contents.
GeneratedFiles = dict[str, str]


class Backend(abc.ABC):
    """Renders an :class:`EdaDesign` into one tool's input files."""

    #: The manifest ``toolflow`` value this backend serves (e.g. ``"verilator"``).
    name: str

    @abc.abstractmethod
    def generate(self, design: EdaDesign) -> GeneratedFiles:
        """Return the tool input files for *design* as ``{filename: text}``."""
