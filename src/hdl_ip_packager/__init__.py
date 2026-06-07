"""HDL IP Packager — package, version, distribute, and resolve HDL IP cores.

This top-level package re-exports the stable public API. Import the pieces you
need directly from here::

    from hdl_ip_packager import Manifest, Vlnv, Version, VersionConstraint

See ``docs/architecture.md`` for the module map and ``docs/progress_tracker.md``
for what is implemented versus planned.
"""

from __future__ import annotations

from .backends import (
    Backend,
    CoreSource,
    EdaDesign,
    EdaFile,
    build_eda_design,
    get_backend,
    supported_toolflows,
)
from .cache import ContentAddressedCache, default_cache_root
from .editing import add_dependency
from .exceptions import (
    BackendError,
    HdlPackagerError,
    InvalidConstraintError,
    InvalidVersionError,
    InvalidVlnvError,
    LockfileError,
    ManifestError,
    PackagingError,
    RegistryError,
    ResolutionError,
)
from .ipxact import IPXACT_NAMESPACE, to_ipxact
from .lockfile import LockedPackage, Lockfile, sha256_digest
from .manifest import MANIFEST_SCHEMA_VERSION, Dependency, Fileset, Manifest, Target
from .packaging import artifact_filename, extract_ipkg, manifest_from_ipkg, pack_core
from .registry import (
    HttpRegistry,
    LocalDirectoryRegistry,
    LocalRegistry,
    Registry,
    available_from_registry,
)
from .resolver import Resolution, resolve
from .sbom import CYCLONEDX_SPEC_VERSION, build_cyclonedx
from .treeview import render_dependency_tree
from .version import Version, VersionConstraint
from .vlnv import PackageRef, Vlnv

__version__ = "0.7.0"

__all__ = [
    "CYCLONEDX_SPEC_VERSION",
    "IPXACT_NAMESPACE",
    "MANIFEST_SCHEMA_VERSION",
    "Backend",
    "BackendError",
    "ContentAddressedCache",
    "CoreSource",
    "Dependency",
    "EdaDesign",
    "EdaFile",
    "Fileset",
    "HdlPackagerError",
    "HttpRegistry",
    "InvalidConstraintError",
    "InvalidVersionError",
    "InvalidVlnvError",
    "LocalDirectoryRegistry",
    "LocalRegistry",
    "LockedPackage",
    "Lockfile",
    "LockfileError",
    "Manifest",
    "ManifestError",
    "PackageRef",
    "PackagingError",
    "Registry",
    "RegistryError",
    "Resolution",
    "ResolutionError",
    "Target",
    "Version",
    "VersionConstraint",
    "Vlnv",
    "__version__",
    "add_dependency",
    "artifact_filename",
    "available_from_registry",
    "build_cyclonedx",
    "build_eda_design",
    "default_cache_root",
    "extract_ipkg",
    "get_backend",
    "manifest_from_ipkg",
    "pack_core",
    "render_dependency_tree",
    "resolve",
    "sha256_digest",
    "supported_toolflows",
    "to_ipxact",
]
