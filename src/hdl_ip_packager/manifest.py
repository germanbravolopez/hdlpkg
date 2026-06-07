"""The IP core manifest (``ip.toml``).

Every IP core in this ecosystem carries an ``ip.toml`` manifest at its root. The
manifest declares the core's identity (VLNV), its metadata, its source filesets,
its dependencies (as version constraints), and its build targets. This is the
direct analogue of ``Cargo.toml`` / ``package.json`` / a FuseSoC ``.core`` file.

Example::

    [package]
    vendor      = "acme"
    library     = "comm"
    name        = "uart"
    version     = "1.2.0"
    description = "AXI-Lite UART with configurable FIFOs"
    license     = "Apache-2.0"
    authors     = ["Jane Doe <jane@acme.com>"]
    top         = "uart_top"
    keywords    = ["uart", "axi", "serial"]

    [dependencies]
    "acme:common:fifo"     = "^1.0.0"
    "vendorx:axi:axil_bfm" = ">=2.1.0,<3.0.0"

    [filesets.rtl]
    files = ["rtl/uart_top.sv", "rtl/uart_fifo.sv"]
    type  = "systemVerilogSource"

    [filesets.tb]
    files = ["tb/uart_tb.sv"]
    type  = "systemVerilogSource"

    [targets.sim]
    toolflow = "verilator"
    filesets = ["rtl", "tb"]
    top      = "uart_tb"

Parsing uses the standard-library ``tomllib`` (Python 3.11+), so there is no
third-party TOML dependency. All validation errors raise :class:`ManifestError`
with a message that names the offending field.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import HdlPackagerError, ManifestError
from .version import Version, VersionConstraint
from .vlnv import PackageRef, Vlnv

__all__ = [
    "MANIFEST_FILENAME",
    "MANIFEST_SCHEMA_VERSION",
    "Dependency",
    "Fileset",
    "Manifest",
    "Target",
]

MANIFEST_FILENAME = "ip.toml"

# The ip.toml schema version this hdlpkg understands. An optional top-level
# ``schema = N`` key lets the format evolve after 1.0 with a clear migration
# path: a manifest written for a newer schema is rejected with a clear message
# rather than mis-parsed. Absent ``schema`` means the original (1) format.
MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Dependency:
    """A single dependency: a version-less :class:`PackageRef` plus a constraint."""

    ref: PackageRef
    constraint: VersionConstraint

    def __str__(self) -> str:
        return f"{self.ref} = {self.constraint}"


@dataclass(frozen=True)
class Fileset:
    """A named group of source files of one HDL type, optionally target-scoped."""

    name: str
    files: tuple[str, ...]
    type: str = "systemVerilogSource"
    depend: tuple[str, ...] = ()


@dataclass(frozen=True)
class Target:
    """A build target: which filesets to feed to which tool flow, and the top unit."""

    name: str
    toolflow: str
    filesets: tuple[str, ...]
    top: str | None = None


@dataclass(frozen=True)
class Manifest:
    """A fully-parsed, validated ``ip.toml``."""

    vlnv: Vlnv
    description: str = ""
    license: str = ""
    authors: tuple[str, ...] = ()
    top: str | None = None
    keywords: tuple[str, ...] = ()
    dependencies: tuple[Dependency, ...] = ()
    filesets: dict[str, Fileset] = field(default_factory=dict)
    targets: dict[str, Target] = field(default_factory=dict)
    schema_version: int = MANIFEST_SCHEMA_VERSION

    # ----------------------------------------------------------------- loaders
    @classmethod
    def from_str(cls, text: str) -> Manifest:
        """Parse a manifest from a TOML string."""
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ManifestError(f"Invalid TOML: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_path(cls, path: str | Path) -> Manifest:
        """Parse a manifest from an ``ip.toml`` file on disk."""
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ManifestError(f"Cannot read manifest {path}: {exc}") from exc
        try:
            return cls.from_str(text)
        except ManifestError as exc:
            raise ManifestError(f"In {path}: {exc}") from exc

    # ------------------------------------------------------------- validation
    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Manifest:
        """Build and validate a manifest from an already-parsed mapping."""
        schema = cls._parse_schema(data.get("schema", MANIFEST_SCHEMA_VERSION))

        pkg = data.get("package")
        if not isinstance(pkg, dict):
            raise ManifestError("Missing required [package] table.")

        vlnv = cls._parse_identity(pkg)
        dependencies = cls._parse_dependencies(data.get("dependencies", {}))
        filesets = cls._parse_filesets(data.get("filesets", {}))
        targets = cls._parse_targets(data.get("targets", {}), filesets)

        return cls(
            vlnv=vlnv,
            description=str(pkg.get("description", "")),
            license=str(pkg.get("license", "")),
            authors=cls._str_tuple(pkg.get("authors", []), "package.authors"),
            top=pkg.get("top"),
            keywords=cls._str_tuple(pkg.get("keywords", []), "package.keywords"),
            dependencies=dependencies,
            filesets=filesets,
            targets=targets,
            schema_version=schema,
        )

    @staticmethod
    def _parse_schema(value: object) -> int:
        """Validate the optional top-level ``schema`` version (defaults to 1)."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ManifestError(f"Top-level 'schema' must be an integer, got {value!r}.")
        if value != MANIFEST_SCHEMA_VERSION:
            raise ManifestError(
                f"Unsupported ip.toml schema version {value}; this hdlpkg supports "
                f"{MANIFEST_SCHEMA_VERSION}. Upgrade hdlpkg or migrate the manifest."
            )
        return value

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _require(table: dict[str, object], key: str, where: str) -> object:
        if key not in table:
            raise ManifestError(f"Missing required key '{key}' in [{where}].")
        return table[key]

    @staticmethod
    def _str_tuple(value: object, where: str) -> tuple[str, ...]:
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ManifestError(f"'{where}' must be a list of strings.")
        return tuple(value)

    @classmethod
    def _parse_identity(cls, pkg: dict[str, object]) -> Vlnv:
        vendor = cls._require(pkg, "vendor", "package")
        library = cls._require(pkg, "library", "package")
        name = cls._require(pkg, "name", "package")
        version = cls._require(pkg, "version", "package")
        if not isinstance(version, str):
            raise ManifestError("package.version must be a string.")
        try:
            ref = PackageRef(str(vendor), str(library), str(name))
            return ref.with_version(Version.parse(version))
        except HdlPackagerError as exc:
            raise ManifestError(f"Invalid package identity: {exc}") from exc

    @classmethod
    def _parse_dependencies(cls, table: object) -> tuple[Dependency, ...]:
        if not isinstance(table, dict):
            raise ManifestError("[dependencies] must be a table.")
        deps: list[Dependency] = []
        for key, value in table.items():
            if not isinstance(value, str):
                raise ManifestError(
                    f"Dependency '{key}' must map to a constraint string, "
                    f"got {type(value).__name__}."
                )
            try:
                ref = PackageRef.parse(key)
                constraint = VersionConstraint.parse(value)
            except HdlPackagerError as exc:
                raise ManifestError(f"Invalid dependency '{key}': {exc}") from exc
            deps.append(Dependency(ref=ref, constraint=constraint))
        return tuple(deps)

    @classmethod
    def _parse_filesets(cls, table: object) -> dict[str, Fileset]:
        if not isinstance(table, dict):
            raise ManifestError("[filesets] must be a table.")
        out: dict[str, Fileset] = {}
        for name, body in table.items():
            if not isinstance(body, dict):
                raise ManifestError(f"[filesets.{name}] must be a table.")
            raw_files = cls._require(body, "files", f"filesets.{name}")
            files = cls._str_tuple(raw_files, f"filesets.{name}.files")
            out[name] = Fileset(
                name=name,
                files=files,
                type=str(body.get("type", "systemVerilogSource")),
                depend=cls._str_tuple(body.get("depend", []), f"filesets.{name}.depend"),
            )
        return out

    @classmethod
    def _parse_targets(cls, table: object, filesets: dict[str, Fileset]) -> dict[str, Target]:
        if not isinstance(table, dict):
            raise ManifestError("[targets] must be a table.")
        out: dict[str, Target] = {}
        for name, body in table.items():
            if not isinstance(body, dict):
                raise ManifestError(f"[targets.{name}] must be a table.")
            toolflow = str(cls._require(body, "toolflow", f"targets.{name}"))
            target_filesets = cls._str_tuple(body.get("filesets", []), f"targets.{name}.filesets")
            for fs in target_filesets:
                if fs not in filesets:
                    raise ManifestError(
                        f"Target '{name}' references unknown fileset '{fs}'. "
                        f"Known filesets: {sorted(filesets) or '(none)'}."
                    )
            top = body.get("top")
            if top is not None and not isinstance(top, str):
                raise ManifestError(f"targets.{name}.top must be a string.")
            out[name] = Target(name=name, toolflow=toolflow, filesets=target_filesets, top=top)
        return out

    # ----------------------------------------------------------- convenience
    @property
    def ref(self) -> PackageRef:
        """The version-less reference for this core."""
        return self.vlnv.ref
