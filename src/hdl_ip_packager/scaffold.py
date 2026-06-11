"""Starter-manifest scaffolding for ``hdlpkg init``.

This module renders a fresh, ready-to-edit ``ip.toml`` from a small set of
identity and metadata fields. It is the pure core behind the ``hdlpkg init``
command: it performs no I/O, so the CLI layer owns prompting for the fields and
writing the file to disk.

The rendered text is deliberately a *valid* manifest -- it round-trips through
:class:`~hdl_ip_packager.manifest.Manifest`, so a freshly scaffolded core passes
``hdlpkg validate`` immediately and gives the author a working skeleton (one
fileset, one simulation target) to grow from.
"""

from __future__ import annotations

from dataclasses import dataclass

from .version import (
    DEFAULT_VERSION_SCHEME,
    AnyVersion,
    CalVer,
    MonotonicVersion,
    OpaqueVersion,
    Version,
    VersionScheme,
    parse_version,
)
from .vlnv import PackageRef, Vlnv

__all__ = ["ScaffoldOptions", "render_manifest"]

# The default version a brand-new, unreleased core starts at (SemVer 0.y.z).
DEFAULT_VERSION = "0.1.0"


def _toml_basic_string(value: str) -> str:
    """Render *value* as a TOML basic (double-quoted) string, escaping specials."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass(frozen=True)
class ScaffoldOptions:
    """The fields needed to scaffold a starter manifest, validated on construction.

    ``vendor``/``library``/``name`` are validated as VLNV segments and ``version``
    is parsed under ``scheme`` (SemVer by default, or one of the non-SemVer schemes
    for vendor/date version codes); ``top`` defaults to ``name`` so the rendered
    target is consistent.
    """

    vendor: str
    library: str
    name: str
    version: AnyVersion
    scheme: VersionScheme = DEFAULT_VERSION_SCHEME
    description: str = ""
    license: str = ""
    top: str | None = None

    def __post_init__(self) -> None:
        # Reuse the canonical segment validation; raises InvalidVlnvError on a bad part.
        PackageRef(self.vendor, self.library, self.name)
        if not isinstance(self.version, (Version, OpaqueVersion, CalVer, MonotonicVersion)):
            raise TypeError(f"version must be a parsed version, got {type(self.version).__name__}")

    @classmethod
    def create(
        cls,
        vendor: str,
        library: str,
        name: str,
        version: str = DEFAULT_VERSION,
        scheme: VersionScheme = DEFAULT_VERSION_SCHEME,
        description: str = "",
        license: str = "",
        top: str | None = None,
    ) -> ScaffoldOptions:
        """Build options from strings, parsing *version* under *scheme*; raise on bad input."""
        return cls(
            vendor=vendor,
            library=library,
            name=name,
            version=parse_version(version, scheme),
            scheme=scheme,
            description=description,
            license=license,
            top=top,
        )

    @property
    def effective_top(self) -> str:
        """The top-level unit name, defaulting to the core name when unset."""
        return self.top if self.top else self.name

    @property
    def vlnv(self) -> Vlnv:
        """The fully-qualified identity of the core being scaffolded."""
        return PackageRef(self.vendor, self.library, self.name).with_version(self.version)


def render_manifest(options: ScaffoldOptions) -> str:
    """Render a complete, valid starter ``ip.toml`` for *options*."""
    name = options.name
    top = options.effective_top
    lines = [
        "[package]",
        f"vendor      = {_toml_basic_string(options.vendor)}",
        f"library     = {_toml_basic_string(options.library)}",
        f"name        = {_toml_basic_string(name)}",
        f"version     = {_toml_basic_string(str(options.version))}",
        # Only emit a non-default scheme; a plain SemVer core stays scheme-less.
        *(
            [f"scheme      = {_toml_basic_string(options.scheme)}"]
            if options.scheme != DEFAULT_VERSION_SCHEME
            else []
        ),
        f"description = {_toml_basic_string(options.description)}",
        f"license     = {_toml_basic_string(options.license)}",
        "authors     = []",
        f"top         = {_toml_basic_string(top)}",
        "",
        "[dependencies]",
        '# "vendor:library:name" = "^1.0.0"',
        "",
        "[filesets.rtl]",
        f'files = ["rtl/{name}.sv"]',
        'type  = "systemVerilogSource"',
        "",
        "[targets.sim]",
        'toolflow = "verilator"',
        'filesets = ["rtl"]',
        f"top      = {_toml_basic_string(top)}",
        "",
    ]
    return "\n".join(lines)
