"""Tool-flow generation backends.

The ``gen`` command builds a tool-agnostic :class:`EdaDesign` from a resolved
design (:mod:`~hdl_ip_packager.backends.edam`) and hands it to a :class:`Backend`
selected by the target's ``toolflow`` (:func:`get_backend`). Backends are pure:
they return ``{filename: text}`` and never touch the filesystem.
"""

from __future__ import annotations

from ..exceptions import BackendError
from .base import Backend, GeneratedFiles
from .edam import CoreSource, EdaDesign, EdaFile, build_eda_design, normalize_file_type
from .ghdl import GhdlBackend
from .icarus import IcarusBackend
from .verilator import VerilatorBackend
from .vivado import VivadoBackend
from .yosys import YosysBackend

__all__ = [
    "Backend",
    "CoreSource",
    "EdaDesign",
    "EdaFile",
    "GeneratedFiles",
    "build_eda_design",
    "get_backend",
    "normalize_file_type",
    "supported_toolflows",
]

# Registry of tool-flow backends, keyed by the manifest ``toolflow`` name.
_BACKENDS: dict[str, Backend] = {
    backend.name: backend
    for backend in (
        VerilatorBackend(),
        VivadoBackend(),
        IcarusBackend(),
        GhdlBackend(),
        YosysBackend(),
    )
}


def supported_toolflows() -> list[str]:
    """The tool-flow names a backend exists for (sorted)."""
    return sorted(_BACKENDS)


def get_backend(toolflow: str) -> Backend:
    """Return the backend for *toolflow*; raise :class:`BackendError` if none exists."""
    backend = _BACKENDS.get(toolflow)
    if backend is None:
        raise BackendError(
            f"No backend for tool flow {toolflow!r}; available: {', '.join(supported_toolflows())}."
        )
    return backend
