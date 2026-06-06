"""The tool-agnostic intermediate design description (an EDAM-like model).

``gen`` turns a resolved design -- the root core plus its resolved dependencies --
and a chosen build *target* into a flat, ordered list of source files with a top
unit and a tool flow. That intermediate (:class:`EdaDesign`) is what a tool
*backend* (Verilator, Vivado, ...) consumes, so tool specifics never leak into the
resolver, manifest, or packaging layers. The name nods to FuseSoC's EDAM.

This module is **pure**: it does no filesystem access. The caller supplies each
core's on-disk root as a string and :func:`build_eda_design` only joins paths and
re-orders metadata, so the whole assembly is unit-testable without real sources.

Fileset selection (the M6 semantics; see ``docs/architecture.md`` and the
non-blocking issue on richer selection):

* The **root** contributes the filesets named by the selected target -- so a
  ``sim`` target pulls in its testbench, a ``synth`` target does not.
* A **dependency** contributes its synthesizable surface only: its fileset named
  ``rtl`` if present, otherwise every fileset whose name is not a known testbench
  name. A dependency's testbench is never compiled into a dependent's build.
* Any selected fileset also pulls in its declared ``depend`` filesets (transitively,
  emitted before it), so a core can state exactly what a fileset needs instead of
  relying on the ``rtl``/``tb`` naming convention alone.

Cores are emitted **dependencies first** (topologically ordered, dependents after
their dependencies, ties broken by VLNV) so file order is valid for tools that
care about compile order; the root core comes last.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePath

from ..manifest import Manifest
from ..vlnv import PackageRef

__all__ = [
    "EdaDesign",
    "EdaFile",
    "build_eda_design",
    "normalize_file_type",
]

# Fileset names treated as testbench-only, so a dependency never exports them.
_TESTBENCH_FILESETS = frozenset({"tb", "test", "testbench", "bench", "verification"})

# IP-XACT-style fileType vocabulary (lowercased) -> the kind backends switch on.
_FILE_TYPES = {
    "systemverilogsource": "systemVerilog",
    "verilogsource": "verilog",
    "vhdlsource": "vhdl",
    "vhdlsource-93": "vhdl",
    "vhdlsource-2008": "vhdl",
}


def normalize_file_type(raw: str) -> str:
    """Map a manifest fileset ``type`` to a normalized HDL kind.

    Returns one of ``systemVerilog``, ``verilog``, ``vhdl``, or -- for anything
    unrecognized -- the original string unchanged, so a backend can reject it with
    a clear message rather than silently dropping the file.
    """
    return _FILE_TYPES.get(raw.lower(), raw)


@dataclass(frozen=True)
class EdaFile:
    """One source file in a generated design."""

    path: str
    file_type: str
    core: str  # the VLNV string of the core that owns this file (for traceability)


@dataclass(frozen=True)
class EdaDesign:
    """A flat, tool-agnostic description of what to build for one target."""

    name: str
    toplevel: str | None
    toolflow: str
    files: tuple[EdaFile, ...]
    parameters: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CoreSource:
    """A core to draw files from: its parsed manifest and its on-disk root.

    ``root`` is treated as an opaque path string -- it is only joined with fileset
    paths, never read -- so assembly stays pure.
    """

    manifest: Manifest
    root: str


def _expand_fileset_names(manifest: Manifest, names: Sequence[str]) -> list[str]:
    """Expand *names* with each fileset's ``depend`` closure.

    A fileset may declare ``depend = [...]`` naming other filesets it needs; those
    are emitted **before** it (and transitively), de-duplicated, so a core controls
    exactly what a selected fileset drags in instead of relying on naming alone.
    Unknown names and dependency cycles are skipped safely.
    """
    ordered: list[str] = []
    placed: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in placed or name in visiting:
            return  # already emitted, or a cycle -- stop
        fileset = manifest.filesets.get(name)
        if fileset is None:
            return  # a target/depend may name a fileset that does not exist
        visiting.add(name)
        for dependency in fileset.depend:
            visit(dependency)
        visiting.discard(name)
        placed.add(name)
        ordered.append(name)

    for name in names:
        visit(name)
    return ordered


def _fileset_files(core: CoreSource, fileset_names: Sequence[str]) -> list[EdaFile]:
    """Resolve the files of the named filesets of *core* (plus their ``depend``
    closure) into ordered EdaFiles."""
    out: list[EdaFile] = []
    vlnv = str(core.manifest.vlnv)
    for name in _expand_fileset_names(core.manifest, fileset_names):
        fileset = core.manifest.filesets[name]  # _expand only yields existing names
        file_type = normalize_file_type(fileset.type)
        for rel in fileset.files:
            out.append(
                EdaFile(path=PurePath(core.root, rel).as_posix(), file_type=file_type, core=vlnv)
            )
    return out


def _dependency_fileset_names(manifest: Manifest) -> list[str]:
    """The filesets a dependency exports: its ``rtl`` surface, or all non-testbench."""
    if "rtl" in manifest.filesets:
        return ["rtl"]
    return [name for name in manifest.filesets if name not in _TESTBENCH_FILESETS]


def _topological_order(dependencies: Sequence[CoreSource]) -> list[CoreSource]:
    """Order *dependencies* so each core follows the deps it references (ties by VLNV)."""
    by_ref: dict[PackageRef, CoreSource] = {c.manifest.ref: c for c in dependencies}
    ordered: list[CoreSource] = []
    visiting: set[PackageRef] = set()
    placed: set[PackageRef] = set()

    def visit(core: CoreSource) -> None:
        ref = core.manifest.ref
        if ref in placed or ref in visiting:
            return  # already done, or a cycle (resolution forbids these) -- stop
        visiting.add(ref)
        for dep in sorted(core.manifest.dependencies, key=lambda d: str(d.ref)):
            child = by_ref.get(dep.ref)
            if child is not None:
                visit(child)
        visiting.discard(ref)
        placed.add(ref)
        ordered.append(core)

    for core in sorted(dependencies, key=lambda c: str(c.manifest.vlnv)):
        visit(core)
    return ordered


def build_eda_design(
    root: CoreSource,
    target: str,
    dependencies: Sequence[CoreSource],
) -> EdaDesign:
    """Assemble the :class:`EdaDesign` for *root*'s *target* plus its *dependencies*.

    Args:
        root: the top-level core (its selected target drives the build).
        target: the name of a ``[targets.*]`` table in the root manifest.
        dependencies: the resolved dependency cores (any order; reordered here).

    Raises:
        KeyError: never -- an unknown target raises :class:`ValueError` instead.
        ValueError: if *target* is not defined in the root manifest.
    """
    spec = root.manifest.targets.get(target)
    if spec is None:
        known = ", ".join(sorted(root.manifest.targets)) or "(none)"
        raise ValueError(f"Unknown target {target!r}; the manifest defines: {known}.")

    files: list[EdaFile] = []
    seen: set[str] = set()

    def add(eda_files: list[EdaFile]) -> None:
        for f in eda_files:
            if f.path not in seen:
                seen.add(f.path)
                files.append(f)

    for dep in _topological_order(dependencies):
        add(_fileset_files(dep, _dependency_fileset_names(dep.manifest)))
    add(_fileset_files(root, spec.filesets))

    return EdaDesign(
        name=root.manifest.vlnv.name,
        toplevel=spec.top or root.manifest.top,
        toolflow=spec.toolflow,
        files=tuple(files),
    )
