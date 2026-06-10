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

from ..exceptions import BackendError
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


def _reject_multiversion(dependencies: Sequence[CoreSource]) -> None:
    """Refuse to assemble two versions of one package without mangling.

    HDL puts every ``module``/``package`` name in one global namespace, so two
    versions of a core collide at elaboration. The CLI's ``gen`` first name-mangles
    coexisting SystemVerilog *packages* (then calls this with ``allow_multiversion``);
    reaching here means that did not happen, so it stops with a clear message rather
    than emitting a design that cannot elaborate.
    """
    versions_by_ref: dict[PackageRef, set[str]] = {}
    for core in dependencies:
        versions_by_ref.setdefault(core.manifest.ref, set()).add(str(core.manifest.vlnv.version))
    conflicted = {ref: vers for ref, vers in versions_by_ref.items() if len(vers) > 1}
    if conflicted:
        ref, vers = next(iter(sorted(conflicted.items(), key=lambda kv: str(kv[0]))))
        listed = ", ".join(sorted(vers))
        raise BackendError(
            f"Cannot generate a design with two versions of {ref} ({listed}): HDL elaboration "
            f"cannot host two versions of one package in a single namespace. Generate under "
            f"[resolution] on-conflict = 'isolate_namespaces' (which name-mangles SystemVerilog/"
            f"VHDL packages), resolve to a single version ('use_latest'), or split the build."
        )


def _topological_order(dependencies: Sequence[CoreSource]) -> list[CoreSource]:
    """Order *dependencies* so each core follows the deps it references (ties by VLNV).

    Keyed by VLNV (not the version-less ref) so two versions of one package -- present
    under the ``isolate_namespaces`` policy -- both appear, each before its dependents.
    """
    by_ref: dict[PackageRef, list[CoreSource]] = {}
    for core in dependencies:
        by_ref.setdefault(core.manifest.ref, []).append(core)
    ordered: list[CoreSource] = []
    visiting: set[str] = set()
    placed: set[str] = set()

    def visit(core: CoreSource) -> None:
        key = str(core.manifest.vlnv)
        if key in placed or key in visiting:
            return  # already done, or a cycle (resolution forbids these) -- stop
        visiting.add(key)
        for dep in sorted(core.manifest.dependencies, key=lambda d: str(d.ref)):
            for child in by_ref.get(dep.ref, []):
                visit(child)
        visiting.discard(key)
        placed.add(key)
        ordered.append(core)

    for core in sorted(dependencies, key=lambda c: str(c.manifest.vlnv)):
        visit(core)
    return ordered


def build_eda_design(
    root: CoreSource,
    target: str,
    dependencies: Sequence[CoreSource],
    allow_multiversion: bool = False,
) -> EdaDesign:
    """Assemble the :class:`EdaDesign` for *root*'s *target* plus its *dependencies*.

    Args:
        root: the top-level core (its selected target drives the build).
        target: the name of a ``[targets.*]`` table in the root manifest.
        dependencies: the resolved dependency cores (any order; reordered here).
        allow_multiversion: if False (default) two versions of one package are refused
            (they collide in one HDL namespace). The CLI sets it True only after
            name-mangling the sources, so the colliding names no longer clash.

    Raises:
        ValueError: if *target* is not defined in the root manifest.
        BackendError: if two versions of one package are present and not allowed.
    """
    spec = root.manifest.targets.get(target)
    if spec is None:
        known = ", ".join(sorted(root.manifest.targets)) or "(none)"
        raise ValueError(f"Unknown target {target!r}; the manifest defines: {known}.")

    if not allow_multiversion:
        _reject_multiversion(dependencies)

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
