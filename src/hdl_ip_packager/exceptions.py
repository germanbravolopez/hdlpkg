"""Exception hierarchy for the HDL IP Packager.

Every error the package raises derives from :class:`HdlPackagerError`, so callers
(the CLI, other tools embedding the library) can catch the whole family with a
single ``except``. Keep new exception types here so the hierarchy stays in one
place and is easy to document.
"""

from __future__ import annotations


class HdlPackagerError(Exception):
    """Base class for every error raised by the HDL IP Packager."""


class InvalidVersionError(HdlPackagerError, ValueError):
    """A version string is not valid semantic versioning."""


class InvalidConstraintError(HdlPackagerError, ValueError):
    """A version-constraint string could not be parsed."""


class InvalidVlnvError(HdlPackagerError, ValueError):
    """A VLNV (vendor:library:name:version) identifier is malformed."""


class ManifestError(HdlPackagerError):
    """An IP manifest (``ip.toml``) is missing required data or is malformed."""


class ResolutionError(HdlPackagerError):
    """The dependency resolver could not satisfy the requested constraints."""


class RegistryError(HdlPackagerError):
    """A registry/cache operation (fetch, publish, lookup) failed."""
