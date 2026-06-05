"""HDL IP Packager — package, version, distribute, and resolve HDL IP cores.

This top-level package re-exports the stable public API. Import the pieces you
need directly from here::

    from hdl_ip_packager import Manifest, Vlnv, Version, VersionConstraint

See ``docs/architecture.md`` for the module map and ``docs/progress_tracker.md``
for what is implemented versus planned.
"""

from __future__ import annotations

from .exceptions import (
    HdlPackagerError,
    InvalidConstraintError,
    InvalidVersionError,
    InvalidVlnvError,
    ManifestError,
    RegistryError,
    ResolutionError,
)
from .manifest import Dependency, Fileset, Manifest, Target
from .version import Version, VersionConstraint
from .vlnv import PackageRef, Vlnv

__version__ = "0.0.1"

__all__ = [
    "Dependency",
    "Fileset",
    "HdlPackagerError",
    "InvalidConstraintError",
    "InvalidVersionError",
    "InvalidVlnvError",
    "Manifest",
    "ManifestError",
    "PackageRef",
    "RegistryError",
    "ResolutionError",
    "Target",
    "Version",
    "VersionConstraint",
    "Vlnv",
    "__version__",
]
