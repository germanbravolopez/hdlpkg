"""VLNV identifiers — the canonical way to name an IP core.

VLNV (**V**endor : **L**ibrary : **N**ame : **V**ersion) is the identity scheme
used by the IP-XACT standard (IEEE 1685) and by HDL package managers such as
FuseSoC. We adopt it so cores have a globally meaningful, collision-resistant
name, e.g.::

    acme:comm:uart:1.2.0

Two value types live here:

* :class:`PackageRef` — the version-less ``vendor:library:name`` triple, used as
  a dependency *key* (the version comes from a separate constraint).
* :class:`Vlnv` — a fully-qualified ``vendor:library:name:version`` identifier of
  one concrete release.

Pure module: parsing/formatting only, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .exceptions import InvalidVersionError, InvalidVlnvError
from .version import (
    AnyVersion,
    CalVer,
    MonotonicVersion,
    OpaqueVersion,
    Version,
    VersionScheme,
    parse_version,
)

__all__ = ["PackageRef", "Vlnv"]

# A name segment: starts alphanumeric, then alphanumerics plus _ . - (no ':').
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _validate_segment(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SEGMENT_RE.match(value):
        raise InvalidVlnvError(
            f"Invalid {field} segment {value!r}: must start with a letter or digit and "
            f"contain only letters, digits, '_', '.', or '-'."
        )
    return value


@dataclass(frozen=True)
class PackageRef:
    """A version-less core reference: ``vendor:library:name``."""

    vendor: str
    library: str
    name: str

    def __post_init__(self) -> None:
        _validate_segment(self.vendor, "vendor")
        _validate_segment(self.library, "library")
        _validate_segment(self.name, "name")

    @classmethod
    def parse(cls, text: str) -> PackageRef:
        """Parse ``vendor:library:name``; raise :class:`InvalidVlnvError` on failure."""
        if not isinstance(text, str):
            raise InvalidVlnvError(f"VLNV ref must be a string, got {type(text).__name__}")
        parts = text.strip().split(":")
        if len(parts) != 3:
            raise InvalidVlnvError(
                f"Expected 'vendor:library:name' (3 colon-separated parts), got {text!r}"
            )
        return cls(*parts)

    def with_version(self, version: AnyVersion | str) -> Vlnv:
        """Return a fully-qualified :class:`Vlnv` by attaching *version*.

        A string is parsed as SemVer; pass an :class:`OpaqueVersion` instance for an
        opaque-scheme core.
        """
        if isinstance(version, str):
            try:
                version = Version.parse(version)
            except InvalidVersionError as exc:
                raise InvalidVlnvError(str(exc)) from exc
        return Vlnv(self.vendor, self.library, self.name, version)

    def __str__(self) -> str:
        return f"{self.vendor}:{self.library}:{self.name}"


@dataclass(frozen=True)
class Vlnv:
    """A fully-qualified core identity: ``vendor:library:name:version``."""

    vendor: str
    library: str
    name: str
    version: AnyVersion

    def __post_init__(self) -> None:
        _validate_segment(self.vendor, "vendor")
        _validate_segment(self.library, "library")
        _validate_segment(self.name, "name")
        if not isinstance(self.version, (Version, OpaqueVersion, CalVer, MonotonicVersion)):
            raise InvalidVlnvError(
                f"version must be a Version/OpaqueVersion/CalVer/MonotonicVersion, "
                f"got {type(self.version).__name__}"
            )

    @classmethod
    def parse(cls, text: str, scheme: VersionScheme = "semver") -> Vlnv:
        """Parse ``vendor:library:name:version``; raise :class:`InvalidVlnvError` on failure.

        *scheme* selects how the version segment is parsed: ``"semver"`` (default) or
        ``"opaque"`` (a non-SemVer token, e.g. from an opaque-scheme lockfile entry).
        """
        if not isinstance(text, str):
            raise InvalidVlnvError(f"VLNV must be a string, got {type(text).__name__}")
        parts = text.strip().split(":")
        if len(parts) != 4:
            raise InvalidVlnvError(
                f"Expected 'vendor:library:name:version' (4 colon-separated parts), got {text!r}"
            )
        vendor, library, name, version_str = parts
        try:
            version: AnyVersion = parse_version(version_str, scheme)
        except InvalidVersionError as exc:
            raise InvalidVlnvError(f"In VLNV {text!r}: {exc}") from exc
        return cls(vendor, library, name, version)

    @property
    def ref(self) -> PackageRef:
        """The version-less :class:`PackageRef` for this identity."""
        return PackageRef(self.vendor, self.library, self.name)

    def __str__(self) -> str:
        return f"{self.vendor}:{self.library}:{self.name}:{self.version}"
