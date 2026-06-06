"""HDL IP Packager — package, version, distribute, and resolve HDL IP cores.

This top-level package re-exports the stable public API. Import the pieces you
need directly from here::

    from hdl_ip_packager import Manifest, Vlnv, Version, VersionConstraint

See ``docs/architecture.md`` for the module map and ``docs/progress_tracker.md``
for what is implemented versus planned.
"""

from __future__ import annotations

from .cache import ContentAddressedCache, default_cache_root
from .exceptions import (
    HdlPackagerError,
    InvalidConstraintError,
    InvalidVersionError,
    InvalidVlnvError,
    LockfileError,
    ManifestError,
    RegistryError,
    ResolutionError,
)
from .lockfile import LockedPackage, Lockfile, sha256_digest
from .manifest import Dependency, Fileset, Manifest, Target
from .resolver import Resolution, resolve
from .version import Version, VersionConstraint
from .vlnv import PackageRef, Vlnv

__version__ = "0.2.0"

__all__ = [
    "ContentAddressedCache",
    "Dependency",
    "Fileset",
    "HdlPackagerError",
    "InvalidConstraintError",
    "InvalidVersionError",
    "InvalidVlnvError",
    "LockedPackage",
    "Lockfile",
    "LockfileError",
    "Manifest",
    "ManifestError",
    "PackageRef",
    "RegistryError",
    "Resolution",
    "ResolutionError",
    "Target",
    "Version",
    "VersionConstraint",
    "Vlnv",
    "__version__",
    "default_cache_root",
    "resolve",
    "sha256_digest",
]
