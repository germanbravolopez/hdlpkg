"""The tool-flow backend interface.

A *backend* turns the tool-agnostic :class:`~hdl_ip_packager.backends.edam.EdaDesign`
into the concrete input files one EDA tool consumes (a Verilator ``.vc`` command
file, a Vivado source ``.tcl`` script, ...). Backends are **pure**: ``generate``
returns a ``{filename: text}`` mapping and writes nothing; the CLI layer writes
those files to disk. Each backend is keyed by the manifest ``toolflow`` name.
"""

from __future__ import annotations

import abc
import re

from ..exceptions import BackendError
from .edam import EdaDesign

__all__ = ["Backend", "GeneratedFiles"]

# A backend's output: relative filename -> file contents.
GeneratedFiles = dict[str, str]

# A safe HDL top/module identifier. Generated scripts interpolate the top name into
# shell/Tcl commands, so we reject anything that is not a plain identifier (spaces,
# shell metacharacters, ...) rather than emit a malformed or injectable script.
_MODULE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class Backend(abc.ABC):
    """Renders an :class:`EdaDesign` into one tool's input files."""

    #: The manifest ``toolflow`` value this backend serves (e.g. ``"verilator"``).
    name: str

    @abc.abstractmethod
    def generate(self, design: EdaDesign) -> GeneratedFiles:
        """Return the tool input files for *design* as ``{filename: text}``."""

    # ----------------------------------------------------------- shared guards
    def _require_top(self, design: EdaDesign) -> str:
        """Return the design's top, or raise if it is missing or not a safe identifier."""
        if design.toplevel is None:
            raise BackendError(
                f"{self.name} needs a top unit, but the target for {design.name!r} declares none."
            )
        return self._validated_top(design.toplevel)

    def _validated_top(self, top: str) -> str:
        """Return *top* if it is a safe HDL identifier, else raise :class:`BackendError`."""
        if not _MODULE_NAME_RE.match(top):
            raise BackendError(
                f"{self.name}: unsafe top name {top!r}; expected an HDL identifier "
                f"(letters, digits, '_', '$')."
            )
        return top

    def _reject_unsupported(self, design: EdaDesign, supported: frozenset[str]) -> None:
        """Raise :class:`BackendError` if the design has a file type this backend can't handle."""
        unsupported = sorted({f.file_type for f in design.files if f.file_type not in supported})
        if unsupported:
            raise BackendError(
                f"{self.name} cannot handle file type(s) {', '.join(unsupported)}; "
                f"it supports {', '.join(sorted(supported))}."
            )
