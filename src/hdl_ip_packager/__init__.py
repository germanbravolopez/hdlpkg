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
from .credentials import (
    Credential,
    CredentialStore,
    default_credentials_path,
    load_credentials,
    load_docker_config,
    parse_docker_config,
    registry_host,
    save_credentials,
)
from .editing import add_dependency
from .exceptions import (
    BackendError,
    CredentialsError,
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
from .mangle import (
    GenCore,
    GenSourceFile,
    ManglePlan,
    declared_modules,
    declared_packages,
    declared_vhdl_entities,
    declared_vhdl_packages,
    mangled_name,
    plan_package_mangling,
    rewrite_sv_packages,
    rewrite_vhdl_packages,
)
from .manifest import (
    MANIFEST_SCHEMA_VERSION,
    SUPPORTED_CONFLICT_POLICIES,
    ConflictPolicy,
    Dependency,
    Fileset,
    Manifest,
    Target,
)
from .packaging import artifact_filename, extract_ipkg, manifest_from_ipkg, pack_core
from .registry import (
    HttpRegistry,
    LocalDirectoryRegistry,
    LocalRegistry,
    OciRegistry,
    Registry,
    available_from_registry,
    parse_bearer_challenge,
    registry_from_location,
)
from .resolver import Resolution, resolve
from .sbom import CYCLONEDX_SPEC_VERSION, build_cyclonedx
from .treeview import render_dependency_tree
from .version import (
    DEFAULT_VERSION_SCHEME,
    SUPPORTED_VERSION_SCHEMES,
    AnyVersion,
    CalVer,
    MonotonicVersion,
    OpaqueVersion,
    Version,
    VersionConstraint,
    VersionScheme,
    compatibility_group,
    parse_version,
)
from .vlnv import PackageRef, Vlnv

__version__ = "1.0.0-rc.1"

__all__ = [
    "CYCLONEDX_SPEC_VERSION",
    "DEFAULT_VERSION_SCHEME",
    "IPXACT_NAMESPACE",
    "MANIFEST_SCHEMA_VERSION",
    "SUPPORTED_CONFLICT_POLICIES",
    "SUPPORTED_VERSION_SCHEMES",
    "AnyVersion",
    "Backend",
    "BackendError",
    "CalVer",
    "ConflictPolicy",
    "ContentAddressedCache",
    "CoreSource",
    "Credential",
    "CredentialStore",
    "CredentialsError",
    "Dependency",
    "EdaDesign",
    "EdaFile",
    "Fileset",
    "GenCore",
    "GenSourceFile",
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
    "ManglePlan",
    "Manifest",
    "ManifestError",
    "MonotonicVersion",
    "OciRegistry",
    "OpaqueVersion",
    "PackageRef",
    "PackagingError",
    "Registry",
    "RegistryError",
    "Resolution",
    "ResolutionError",
    "Target",
    "Version",
    "VersionConstraint",
    "VersionScheme",
    "Vlnv",
    "__version__",
    "add_dependency",
    "artifact_filename",
    "available_from_registry",
    "build_cyclonedx",
    "build_eda_design",
    "compatibility_group",
    "declared_modules",
    "declared_packages",
    "declared_vhdl_entities",
    "declared_vhdl_packages",
    "default_cache_root",
    "default_credentials_path",
    "extract_ipkg",
    "get_backend",
    "load_credentials",
    "load_docker_config",
    "mangled_name",
    "manifest_from_ipkg",
    "pack_core",
    "parse_bearer_challenge",
    "parse_docker_config",
    "parse_version",
    "plan_package_mangling",
    "registry_from_location",
    "registry_host",
    "render_dependency_tree",
    "resolve",
    "rewrite_sv_packages",
    "rewrite_vhdl_packages",
    "save_credentials",
    "sha256_digest",
    "supported_toolflows",
    "to_ipxact",
]
