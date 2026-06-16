"""Command-line interface for the HDL IP Packager (``hdlpkg``).

The CLI is intentionally thin: it parses arguments and delegates to library
functions, so every behaviour stays unit-testable without spawning a process.
Only the commands backed by implemented modules do real work today; the rest
print a clear "not yet implemented" notice and point at the roadmap. The full
intended command set is documented here and in ``docs/architecture.md`` so the
surface is stable as features land.
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from . import __version__
from .backends import CoreSource, build_eda_design, get_backend, normalize_file_type
from .cache import ContentAddressedCache, default_cache_root
from .credentials import (
    default_credentials_path,
    load_credentials,
    load_docker_config,
    registry_host,
    save_credentials,
)
from .editing import add_dependency
from .exceptions import (
    BackendError,
    CredentialsError,
    HdlPackagerError,
    InvalidVlnvError,
    LockfileError,
    ManifestError,
    RegistryError,
)
from .ipxact import DEFAULT_IPXACT_STD, SUPPORTED_IPXACT_STDS, to_ipxact
from .lockfile import LOCKFILE_FILENAME, Lockfile, sha256_digest
from .mangle import GenCore, GenSourceFile, ManglePlan, plan_package_mangling
from .manifest import (
    MANIFEST_FILENAME,
    SUPPORTED_CONFLICT_POLICIES,
    ConflictPolicy,
    Manifest,
)
from .packaging import artifact_filename, expand_fileset_files, extract_ipkg, pack_core
from .registry import (
    LocalDirectoryRegistry,
    Registry,
    available_from_registry,
    registry_from_location,
)
from .resolver import Resolution
from .resolver import resolve as resolve_deps
from .sbom import build_cyclonedx
from .scaffold import DEFAULT_VERSION, ScaffoldOptions, render_manifest
from .treeview import render_dependency_tree
from .version import (
    DEFAULT_VERSION_SCHEME,
    SUPPORTED_VERSION_SCHEMES,
    VersionConstraint,
)
from .vlnv import PackageRef, Vlnv

_REGISTRY_HELP = (
    "a local directory, or a network URL (http(s)://..., oci://..., or git+ssh/https://...); "
    "use 'hdlpkg login' first for a private HTTP/OCI registry"
)


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser (kept separate so tests can use it)."""
    parser = argparse.ArgumentParser(
        prog="hdlpkg",
        description="HDL IP Packager - package, version, and resolve HDL IP cores.",
    )
    parser.add_argument("--version", action="version", version=f"hdlpkg {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_info = sub.add_parser("info", help="show metadata parsed from a manifest")
    p_info.add_argument(
        "path",
        nargs="?",
        default=MANIFEST_FILENAME,
        help=f"path to the manifest (default: ./{MANIFEST_FILENAME})",
    )
    p_info.set_defaults(func=_cmd_info)

    p_validate = sub.add_parser("validate", help="parse and validate a manifest")
    p_validate.add_argument("path", nargs="?", default=MANIFEST_FILENAME)
    p_validate.set_defaults(func=_cmd_validate)

    p_init = sub.add_parser("init", help=f"scaffold a starter {MANIFEST_FILENAME}")
    p_init.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="directory to create the manifest in (default: current directory)",
    )
    p_init.add_argument("--vendor", help="VLNV vendor segment")
    p_init.add_argument("--library", help="VLNV library segment")
    p_init.add_argument("--name", help="VLNV name segment")
    p_init.add_argument(
        "--version", default=DEFAULT_VERSION, help=f"version string (default: {DEFAULT_VERSION})"
    )
    p_init.add_argument(
        "--scheme",
        choices=SUPPORTED_VERSION_SCHEMES,
        default=DEFAULT_VERSION_SCHEME,
        help="how --version is interpreted: 'semver' (default), 'calver', 'monotonic', "
        "or 'opaque' for vendor/date codes that are not SemVer (e.g. D5020204)",
    )
    p_init.add_argument("--description", default="", help="short core description")
    p_init.add_argument("--license", default="", help="SPDX license identifier")
    p_init.add_argument("--top", help="top-level unit (default: the core name)")
    p_init.add_argument(
        "--force", action="store_true", help=f"overwrite an existing {MANIFEST_FILENAME}"
    )
    p_init.set_defaults(func=_cmd_init)

    p_resolve = sub.add_parser(
        "resolve", help=f"resolve dependencies and write {LOCKFILE_FILENAME}"
    )
    p_resolve.add_argument(
        "path",
        nargs="?",
        default=MANIFEST_FILENAME,
        help=f"path to the root manifest (default: ./{MANIFEST_FILENAME})",
    )
    p_resolve.add_argument(
        "--search",
        action="append",
        metavar="DIR",
        help="directory to scan for available cores (repeatable; default: the "
        "manifest's parent directory)",
    )
    p_resolve.add_argument(
        "--output",
        help=f"where to write the lockfile (default: ./{LOCKFILE_FILENAME} next to the manifest)",
    )
    p_resolve.add_argument(
        "--registry",
        metavar="LOCATION",
        help="resolve from a published registry (overrides --search); " + _REGISTRY_HELP,
    )
    _add_conflict_arg(p_resolve)
    p_resolve.set_defaults(func=_cmd_resolve)

    p_install = sub.add_parser(
        "install", help="resolve dependencies and fetch them into the local cache"
    )
    p_install.add_argument(
        "path",
        nargs="?",
        default=MANIFEST_FILENAME,
        help=f"path to the root manifest (default: ./{MANIFEST_FILENAME})",
    )
    p_install.add_argument(
        "--search",
        action="append",
        metavar="DIR",
        help="directory to scan for available cores (repeatable)",
    )
    p_install.add_argument(
        "--cache-dir", metavar="DIR", help="cache root (default: ~/.hdlpkg/cache)"
    )
    p_install.add_argument(
        "--output", help=f"where to write the lockfile (default: ./{LOCKFILE_FILENAME})"
    )
    p_install.add_argument(
        "--locked",
        action="store_true",
        help=f"install exactly from an existing {LOCKFILE_FILENAME} without re-resolving "
        "(reproducible builds); fail if it is missing",
    )
    p_install.add_argument(
        "--registry",
        metavar="LOCATION",
        help="fetch from a published registry (overrides --search); " + _REGISTRY_HELP,
    )
    _add_conflict_arg(p_install)
    p_install.set_defaults(func=_cmd_install)

    p_pack = sub.add_parser("pack", help="package this core into a distributable .ipkg")
    p_pack.add_argument("path", nargs="?", default=MANIFEST_FILENAME, help="path to the manifest")
    p_pack.add_argument("--output", help="output .ipkg path (default: <vlnv>.ipkg in the cwd)")
    p_pack.add_argument(
        "--sbom",
        nargs="?",
        const="",
        default=None,
        metavar="FILE",
        help="also write a CycloneDX SBOM (default path: <vlnv>.cdx.json)",
    )
    p_pack.add_argument(
        "--search",
        action="append",
        metavar="DIR",
        help="directory to scan for dependency cores when building the SBOM "
        "(default: the manifest's parent directory)",
    )
    p_pack.set_defaults(func=_cmd_pack)

    p_publish = sub.add_parser("publish", help="publish this core to a registry")
    p_publish.add_argument(
        "path", nargs="?", default=MANIFEST_FILENAME, help="path to the manifest"
    )
    p_publish.add_argument("--registry", required=True, metavar="LOCATION", help=_REGISTRY_HELP)
    p_publish.set_defaults(func=_cmd_publish)

    p_pull = sub.add_parser("pull", help="download a core from a registry by VLNV")
    p_pull.add_argument("vlnv", help="the core to pull, e.g. acme:common:fifo:1.0.0")
    p_pull.add_argument("--registry", required=True, metavar="LOCATION", help=_REGISTRY_HELP)
    p_pull.add_argument("--output", metavar="DIR", help="extract the core into this directory")
    p_pull.add_argument("--cache-dir", metavar="DIR", help="cache root (default: ~/.hdlpkg/cache)")
    p_pull.set_defaults(func=_cmd_pull)

    p_yank = sub.add_parser("yank", help="hide a published version from new resolves")
    p_yank.add_argument("vlnv", help="the core version to yank, e.g. acme:common:fifo:1.0.0")
    p_yank.add_argument("--registry", required=True, metavar="LOCATION", help=_REGISTRY_HELP)
    p_yank.set_defaults(func=_cmd_yank)

    p_login = sub.add_parser("login", help="store an auth token for a private registry")
    p_login.add_argument(
        "registry", metavar="LOCATION", help="registry URL, e.g. oci://harbor.corp/ip"
    )
    p_login.add_argument(
        "--username",
        "-u",
        help="username for a registry that uses the OCI token-exchange (HTTP Basic) flow; "
        "omit for a direct bearer token",
    )
    p_login.add_argument(
        "--token",
        "--password",
        dest="token",
        help="the bearer token or password (omit to be prompted without echo)",
    )
    p_login.set_defaults(func=_cmd_login)

    p_logout = sub.add_parser("logout", help="remove a stored registry auth token")
    p_logout.add_argument("registry", metavar="LOCATION", help="registry URL to forget")
    p_logout.set_defaults(func=_cmd_logout)

    p_gen = sub.add_parser("gen", help="generate tool-flow inputs for a target")
    p_gen.add_argument("target", help="the [targets.*] to build (e.g. sim, synth)")
    p_gen.add_argument(
        "path", nargs="?", default=MANIFEST_FILENAME, help="path to the root manifest"
    )
    p_gen.add_argument(
        "--search",
        action="append",
        metavar="DIR",
        help="directory to scan for dependency cores (repeatable; default: the "
        "manifest's parent directory)",
    )
    p_gen.add_argument("--output", metavar="DIR", help="output directory (default: ./gen/<target>)")
    p_gen.add_argument(
        "--registry",
        metavar="LOCATION",
        help="fetch dependency sources from a published registry instead of --search "
        "(materialized from the cache); " + _REGISTRY_HELP,
    )
    p_gen.add_argument(
        "--cache-dir",
        metavar="DIR",
        help="cache root for materialized dependencies (default: ~/.hdlpkg/cache)",
    )
    p_gen.add_argument(
        "--locked",
        action="store_true",
        help=f"use the dependency versions pinned in {LOCKFILE_FILENAME} instead of "
        "re-resolving (reproducible generation); with an installed cache this works "
        "offline. Fail if it is missing",
    )
    _add_conflict_arg(p_gen)
    p_gen.set_defaults(func=_cmd_gen)

    p_tree = sub.add_parser("tree", help="print the resolved dependency graph")
    p_tree.add_argument(
        "path", nargs="?", default=MANIFEST_FILENAME, help="path to the root manifest"
    )
    p_tree.add_argument(
        "--search",
        action="append",
        metavar="DIR",
        help="directory to scan for dependency cores (repeatable; default: the "
        "manifest's parent directory)",
    )
    p_tree.add_argument(
        "--registry",
        metavar="LOCATION",
        help="resolve from a published registry (overrides --search); " + _REGISTRY_HELP,
    )
    _add_conflict_arg(p_tree)
    p_tree.set_defaults(func=_cmd_tree)

    p_ipxact = sub.add_parser(
        "export-ipxact", help="export an IP-XACT (IEEE 1685) component description"
    )
    p_ipxact.add_argument("path", nargs="?", default=MANIFEST_FILENAME, help="path to the manifest")
    p_ipxact.add_argument(
        "--output",
        metavar="FILE",
        help="output XML path (default: <vendor>.<library>.<name>.<version>.xml in the cwd)",
    )
    p_ipxact.add_argument(
        "--std",
        choices=SUPPORTED_IPXACT_STDS,
        default=DEFAULT_IPXACT_STD,
        help=f"IEEE 1685 revision to emit (default: {DEFAULT_IPXACT_STD})",
    )
    p_ipxact.set_defaults(func=_cmd_export_ipxact)

    p_add = sub.add_parser("add", help="add or update a dependency in ip.toml")
    p_add.add_argument(
        "dependency",
        help="vendor:library:name[@constraint] (e.g. acme:common:fifo@^1.0.0)",
    )
    p_add.add_argument("path", nargs="?", default=MANIFEST_FILENAME, help="path to the manifest")
    p_add.add_argument(
        "--version",
        metavar="CONSTRAINT",
        help="version constraint (overrides any @constraint; default: *)",
    )
    p_add.set_defaults(func=_cmd_add)

    return parser


def _add_conflict_arg(parser: argparse.ArgumentParser) -> None:
    """Add the ``--on-conflict`` policy override (overrides the manifest's setting)."""
    parser.add_argument(
        "--on-conflict",
        choices=SUPPORTED_CONFLICT_POLICIES,
        default=None,
        dest="on_conflict",
        help="how to handle an incompatible version conflict, overriding the "
        "manifest's [resolution] on-conflict (default: the manifest's value, or "
        "fail_on_conflict)",
    )


def _policy(args: argparse.Namespace) -> ConflictPolicy | None:
    """The CLI conflict-policy override, if any (else None -> use the manifest's)."""
    return getattr(args, "on_conflict", None)


def _print_warnings(resolution: Resolution) -> None:
    """Surface any policy-driven compromises the resolve made."""
    for warning in resolution.warnings:
        print(f"warning: {warning}", file=sys.stderr)


def _load(path: str) -> Manifest:
    return Manifest.from_path(Path(path))


def _cmd_info(args: argparse.Namespace) -> int:
    manifest = _load(args.path)
    print(f"VLNV       : {manifest.vlnv}")
    if manifest.description:
        print(f"Description: {manifest.description}")
    if manifest.license:
        print(f"License    : {manifest.license}")
    if manifest.dependencies:
        print("Dependencies:")
        for dep in manifest.dependencies:
            print(f"  - {dep}")
    if manifest.filesets:
        print(f"Filesets   : {', '.join(sorted(manifest.filesets))}")
    if manifest.targets:
        print(f"Targets    : {', '.join(sorted(manifest.targets))}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    manifest = _load(args.path)
    print(f"OK: {manifest.vlnv} is a valid manifest.")
    return 0


def _require_field(value: str | None, label: str, interactive: bool) -> str:
    """Return *value*, prompting for it when interactive, else raise."""
    if value:
        return value
    if interactive:
        entered = input(f"{label}: ").strip()
        if entered:
            return entered
    raise ManifestError(f"Missing required field '{label}'; pass --{label} or run interactively.")


def _cmd_init(args: argparse.Namespace) -> int:
    target_dir = Path(args.directory)
    manifest_path = target_dir / MANIFEST_FILENAME
    if manifest_path.exists() and not args.force:
        print(
            f"error: {manifest_path} already exists; pass --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    interactive = sys.stdin.isatty()
    options = ScaffoldOptions.create(
        vendor=_require_field(args.vendor, "vendor", interactive),
        library=_require_field(args.library, "library", interactive),
        name=_require_field(args.name, "name", interactive),
        version=args.version,
        scheme=args.scheme,
        description=args.description,
        license=args.license,
        top=args.top,
    )

    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(render_manifest(options), encoding="utf-8")
    vlnv = options.vlnv
    print(f"Created {manifest_path} for {vlnv}")
    return 0


def _resolve_local(
    manifest_path: Path,
    search: list[str] | None,
    policy: ConflictPolicy | None = None,
) -> tuple[Resolution, LocalDirectoryRegistry]:
    """Resolve *manifest_path* against a local-directory registry over *search*."""
    root = Manifest.from_path(manifest_path)
    registry = _local_registry(manifest_path, search)
    resolution = resolve_deps(root, available_from_registry(registry, root), policy)
    return resolution, registry


def _build_lock(resolution: Resolution, registry: Registry) -> Lockfile:
    """Build a lockfile, taking each pinned core's source/checksum from *registry*."""
    sources = {vlnv: registry.source_for(vlnv) for vlnv in resolution.vlnvs}
    checksums = {vlnv: sha256_digest(registry.artifact_bytes(vlnv)) for vlnv in resolution.vlnvs}
    return Lockfile.from_resolution(resolution, sources=sources, checksums=checksums)


def _local_registry(manifest_path: Path, search: list[str] | None) -> LocalDirectoryRegistry:
    """A local-directory registry over *search* (default: the manifest's parent)."""
    search_dirs = search or [str(manifest_path.resolve().parent)]
    return LocalDirectoryRegistry([Path(d) for d in search_dirs])


def _selected_registry(location: str) -> Registry:
    """Build the registry named by a ``--registry`` location, wiring in stored credentials.

    ``hdlpkg login`` credentials win; a ``docker login`` (``~/.docker/config.json``)
    entry for the same host is used as a fallback, so an already-authenticated registry
    works without a second login.
    """
    credentials = load_credentials().with_fallback(load_docker_config())
    return registry_from_location(location, credentials=credentials)


def _reader_registry(manifest_path: Path, args: argparse.Namespace) -> Registry:
    """The registry to resolve/fetch from: a published `--registry`, else a `--search` scan."""
    registry = getattr(args, "registry", None)
    if registry:
        return _selected_registry(registry)
    return _local_registry(manifest_path, args.search)


def _resolve(manifest_path: Path, args: argparse.Namespace) -> tuple[Resolution, Registry]:
    """Resolve *manifest_path* against the selected registry (published or local-scan)."""
    root = Manifest.from_path(manifest_path)
    registry = _reader_registry(manifest_path, args)
    resolution = resolve_deps(root, available_from_registry(registry, root), _policy(args))
    return resolution, registry


def _load_lockfile(manifest_path: Path) -> Lockfile:
    """Load the ``ip.lock`` next to *manifest_path*; raise if it is missing (for --locked)."""
    lock_path = manifest_path.parent / LOCKFILE_FILENAME
    if not lock_path.is_file():
        raise LockfileError(
            f"--locked needs an existing {lock_path}, but none was found; "
            f"run 'hdlpkg resolve' first."
        )
    return Lockfile.from_path(lock_path)


def _cmd_resolve(args: argparse.Namespace) -> int:
    manifest_path = Path(args.path)
    resolution, registry = _resolve(manifest_path, args)
    lock = _build_lock(resolution, registry)
    output = Path(args.output) if args.output else manifest_path.parent / LOCKFILE_FILENAME
    output.write_text(lock.to_toml(), encoding="utf-8")

    _print_warnings(resolution)
    print(f"Resolved {len(resolution.vlnvs)} package(s); wrote {output}")
    for vlnv in resolution.vlnvs:
        print(f"  {vlnv}")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    manifest_path = Path(args.path)
    cache_root = Path(args.cache_dir) if args.cache_dir else default_cache_root()
    cache = ContentAddressedCache(cache_root)

    if args.locked:
        # Reproducible install: fetch exactly what ip.lock pins, no re-resolve, no rewrite.
        lock = _load_lockfile(manifest_path)
        registry = _reader_registry(manifest_path, args)
        fetched = {pkg.vlnv: registry.fetch(pkg.vlnv, cache) for pkg in lock.packages}
        lock.verify(fetched)  # fail closed if any fetched digest disagrees with the lock
        print(
            f"Installed {len(fetched)} locked package(s) into {cache_root} "
            f"(from {LOCKFILE_FILENAME})"
        )
        for pkg in lock.packages:
            print(f"  {pkg.vlnv}")
        return 0

    resolution, registry = _resolve(manifest_path, args)
    lock = _build_lock(resolution, registry)
    fetched = {vlnv: registry.fetch(vlnv, cache) for vlnv in resolution.vlnvs}
    # The just-fetched digests must match what the lockfile pinned (fail closed).
    lock.verify(fetched)

    output = Path(args.output) if args.output else manifest_path.parent / LOCKFILE_FILENAME
    output.write_text(lock.to_toml(), encoding="utf-8")

    _print_warnings(resolution)
    print(f"Installed {len(fetched)} package(s) into {cache_root}; wrote {output}")
    for vlnv in resolution.vlnvs:
        print(f"  {vlnv}")
    return 0


def _cmd_pack(args: argparse.Namespace) -> int:
    manifest_path = Path(args.path)
    manifest = Manifest.from_path(manifest_path)
    data = pack_core(manifest, manifest_path.parent)
    output = Path(args.output) if args.output else Path(artifact_filename(manifest.vlnv))
    output.write_bytes(data)
    print(f"Packed {manifest.vlnv} -> {output} ({len(data)} bytes, {sha256_digest(data)})")

    if args.sbom is not None:
        # Resolve the dependency graph (if any) so the SBOM pins concrete versions.
        dependencies: list[Manifest] = []
        if manifest.dependencies:
            resolution, registry = _resolve_local(manifest_path, args.search)
            dependencies = [registry.manifest(vlnv) for vlnv in resolution.vlnvs]
        vlnv = manifest.vlnv
        sbom_path = (
            Path(args.sbom)
            if args.sbom
            else Path(f"{vlnv.vendor}.{vlnv.library}.{vlnv.name}.{vlnv.version}.cdx.json")
        )
        sbom_path.write_text(build_cyclonedx(manifest, dependencies), encoding="utf-8")
        print(f"Wrote SBOM ({len(dependencies)} dependency component(s)) -> {sbom_path}")
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    manifest_path = Path(args.path)
    manifest = Manifest.from_path(manifest_path)
    registry = _selected_registry(args.registry)
    vlnv = registry.publish_core(manifest, manifest_path.parent)
    print(f"Published {vlnv} to {args.registry}")
    return 0


def _user_vlnv(text: str) -> Vlnv:
    """Parse a user-supplied VLNV, accepting an opaque (non-SemVer) version too.

    The command line carries no scheme, so try SemVer first and fall back to an
    opaque token; if the VLNV is unknown the registry lookup fails clearly afterward.
    """
    try:
        return Vlnv.parse(text)
    except InvalidVlnvError:
        return Vlnv.parse(text, "opaque")


def _cmd_pull(args: argparse.Namespace) -> int:
    vlnv = _user_vlnv(args.vlnv)
    registry = _selected_registry(args.registry)
    cache_root = Path(args.cache_dir) if args.cache_dir else default_cache_root()
    cache = ContentAddressedCache(cache_root)
    digest = registry.fetch(vlnv, cache)
    print(f"Pulled {vlnv} into {cache_root} ({digest})")
    if args.output:
        dest = extract_ipkg(cache.get(digest), Path(args.output))
        print(f"Extracted to {dest}")
    return 0


def _cmd_yank(args: argparse.Namespace) -> int:
    vlnv = _user_vlnv(args.vlnv)
    _selected_registry(args.registry).yank(vlnv)
    print(f"Yanked {vlnv} in {args.registry}")
    return 0


def _cmd_login(args: argparse.Namespace) -> int:
    host = registry_host(args.registry)
    if host is None:
        raise CredentialsError(
            f"{args.registry!r} is a local registry and needs no login; "
            "use an http(s):// or oci:// location."
        )
    prompt = f"Password for {host}: " if args.username else f"Token for {host}: "
    secret = args.token if args.token is not None else getpass.getpass(prompt)
    if not secret:
        raise CredentialsError("No token/password provided.")
    path = default_credentials_path()
    store = load_credentials(path).with_token(host, secret, args.username)
    save_credentials(store, path)
    kind = f"as '{args.username}'" if args.username else "(bearer token)"
    print(f"Stored credentials for {host} {kind} in {path}")
    return 0


def _cmd_logout(args: argparse.Namespace) -> int:
    host = registry_host(args.registry)
    if host is None:
        raise CredentialsError(f"{args.registry!r} is a local registry; nothing to log out of.")
    path = default_credentials_path()
    save_credentials(load_credentials(path).without(host), path)
    print(f"Removed credentials for {host}")
    return 0


def _cmd_gen(args: argparse.Namespace) -> int:
    manifest_path = Path(args.path)
    root = Manifest.from_path(manifest_path)
    if args.target not in root.targets:
        known = ", ".join(sorted(root.targets)) or "(none)"
        raise BackendError(f"Unknown target {args.target!r}; the manifest defines: {known}.")

    cache_root = Path(args.cache_dir) if args.cache_dir else default_cache_root()
    cache = ContentAddressedCache(cache_root)

    registry: Registry | None
    if args.locked:
        # Reproducible generation: pin dependency versions from ip.lock, no re-resolve.
        lock = _load_lockfile(manifest_path)
        dep_specs = [(pkg.vlnv, pkg.checksum) for pkg in lock.packages]
        # Offline-after-install: only touch the registry if a locked artifact is missing
        # from the content-addressed cache. When `install --locked` already populated it,
        # gen needs no network at all -- so a `git+` source never re-clones/fetches.
        need_registry = any(not (checksum and cache.has(checksum)) for _, checksum in dep_specs)
        registry = _reader_registry(manifest_path, args) if need_registry else None
    else:
        resolution, registry = _resolve(manifest_path, args)
        _print_warnings(resolution)
        dep_specs = [(vlnv, "") for vlnv in resolution.vlnvs]
    root_source = _materialize_filesets(
        CoreSource(manifest=root, root=str(manifest_path.resolve().parent))
    )
    try:
        dependencies = [
            _materialize_filesets(_dependency_source(vlnv, checksum, registry, cache, cache_root))
            for vlnv, checksum in dep_specs
        ]
    except RegistryError as exc:
        if args.locked and not args.registry:
            raise BackendError(
                f"{exc} Run 'hdlpkg install {args.path} --locked' to populate the cache "
                "first, or pass --registry/--search."
            ) from exc
        raise

    out_dir = Path(args.output) if args.output else Path("gen") / args.target
    out_dir.mkdir(parents=True, exist_ok=True)

    # Two versions of one package (the isolate_namespaces policy) collide in HDL's one
    # namespace; mangle the SystemVerilog package names into the generated source tree
    # so they can build together. Otherwise sources are referenced in place.
    multiversion = _has_multiversion(dependencies)
    plan: ManglePlan | None = None
    if multiversion:
        root_source, dependencies, plan = _mangle_sources(out_dir, root_source, dependencies)

    design = build_eda_design(
        root_source, args.target, dependencies, allow_multiversion=multiversion
    )
    outputs = get_backend(design.toolflow).generate(design)

    written = []
    for filename, content in outputs.items():
        dest = out_dir / filename
        dest.write_text(content, encoding="utf-8")
        written.append(dest)

    if plan is not None:
        _print_mangle_report(plan)
    print(
        f"Generated {design.toolflow} inputs for {root.vlnv} target {args.target!r} "
        f"({len(design.files)} source file(s)):"
    )
    for dest in written:
        print(f"  {dest}")
    return 0


def _dependency_source(
    vlnv: Vlnv,
    checksum: str,
    registry: Registry | None,
    cache: ContentAddressedCache,
    cache_root: Path,
) -> CoreSource:
    """Locate a dependency's on-disk source tree for ``gen``, materializing if needed.

    Tries, in order: a locked artifact already in the cache (so ``install --locked`` then
    ``gen --locked`` works fully offline); a loose source tree discoverable on disk
    (``--search``/default scan, used in place); otherwise fetch the ``.ipkg`` from the
    selected registry into the cache and extract it. The last two paths let ``gen`` build
    against published/installed cores without their original source trees. *registry* is
    ``None`` only on the all-cached locked path, where the first branch always returns.
    """
    if checksum and cache.has(checksum):
        return _extract_dependency(cache.get(checksum), checksum, cache_root)
    if registry is None:  # locked + uncached + no registry selected
        raise RegistryError(
            f"{vlnv} is not in the cache and no registry is available; "
            f"run 'hdlpkg install --locked' or pass --registry."
        )
    if isinstance(registry, LocalDirectoryRegistry):
        return CoreSource(manifest=registry.manifest(vlnv), root=str(registry.core_dir(vlnv)))
    digest = registry.fetch(vlnv, cache)
    if checksum and digest != checksum:
        # gen --locked must fail closed on drift, exactly like install --locked's
        # lock.verify: a registry serving different bytes than the lock pins is rejected.
        raise LockfileError(f"Checksum mismatch for {vlnv}: locked {checksum}, got {digest}.")
    return _extract_dependency(cache.get(digest), digest, cache_root)


def _extract_dependency(ipkg: bytes, digest: str, cache_root: Path) -> CoreSource:
    """Extract a dependency ``.ipkg`` into a digest-keyed dir under the cache (reused)."""
    dest = cache_root / "src" / digest.split(":")[-1]
    if not (dest / MANIFEST_FILENAME).exists():
        extract_ipkg(ipkg, dest)
    return CoreSource(manifest=Manifest.from_path(dest / MANIFEST_FILENAME), root=str(dest))


def _materialize_filesets(source: CoreSource) -> CoreSource:
    """Expand *source*'s fileset globs/directories against its on-disk root.

    ``gen`` (and its name-mangling pass) joins fileset paths into tool inputs without
    reading the directory, so glob/directory expansion happens here at the I/O boundary:
    each fileset's ``files`` is resolved to concrete relative paths before assembly, and
    everything downstream sees a plain file list.
    """
    core_dir = Path(source.root)
    filesets = {
        name: replace(fs, files=tuple(expand_fileset_files(core_dir, name, fs.files)))
        for name, fs in source.manifest.filesets.items()
    }
    return CoreSource(manifest=replace(source.manifest, filesets=filesets), root=source.root)


def _has_multiversion(dependencies: list[CoreSource]) -> bool:
    """True if two of *dependencies* are different versions of the same package."""
    refs = [str(dep.manifest.ref) for dep in dependencies]
    return len(set(refs)) < len(refs)


def _gen_core(source: CoreSource) -> GenCore:
    """Read *source*'s fileset files into a :class:`GenCore` for mangling."""
    files: list[GenSourceFile] = []
    for fileset in source.manifest.filesets.values():
        language = normalize_file_type(fileset.type).lower()
        for rel in fileset.files:
            text = (Path(source.root) / rel).read_text(encoding="utf-8")
            files.append(
                GenSourceFile(key=(str(source.manifest.vlnv), rel), text=text, language=language)
            )
    return GenCore(manifest=source.manifest, files=tuple(files))


def _mangle_sources(
    out_dir: Path, root_source: CoreSource, dependencies: list[CoreSource]
) -> tuple[CoreSource, list[CoreSource], ManglePlan]:
    """Mangle coexisting unit versions into ``<out_dir>/src`` and re-root the cores.

    Raises ``BackendError`` (via the planner) if the conflict cannot be mangled safely.
    """
    sources = [root_source, *dependencies]
    cores = [_gen_core(source) for source in sources]
    plan = plan_package_mangling(cores)

    rerooted: list[CoreSource] = []
    for source, core in zip(sources, cores, strict=True):
        core_dir = out_dir / "src" / _safe_dirname(str(source.manifest.vlnv))
        for gen_file in core.files:
            rel = gen_file.key[1]
            dest = core_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(plan.rewritten[gen_file.key], encoding="utf-8")
        rerooted.append(CoreSource(manifest=source.manifest, root=str(core_dir)))
    return rerooted[0], rerooted[1:], plan


def _safe_dirname(value: str) -> str:
    """A filesystem-safe directory name for a VLNV (``:`` -> ``_``)."""
    return re.sub(r"[^0-9A-Za-z._-]", "_", value)


def _print_mangle_report(plan: ManglePlan) -> None:
    """Surface the design-unit renames the mangler applied (to stderr)."""
    if not plan.renamed:
        return
    print(
        "warning: incompatible versions coexist (isolate_namespaces); the generated HDL "
        "sources were name-mangled (packages, modules, interfaces, entities) so they can "
        "build together:",
        file=sys.stderr,
    )
    for name, mangled in sorted(plan.renamed.items()):
        print(f"  {name} -> {', '.join(mangled)}", file=sys.stderr)


def _cmd_tree(args: argparse.Namespace) -> int:
    manifest_path = Path(args.path)
    root = Manifest.from_path(manifest_path)
    resolution, registry = _resolve(manifest_path, args)
    manifests = {vlnv: registry.manifest(vlnv) for vlnv in resolution.vlnvs}
    _print_warnings(resolution)
    print(render_dependency_tree(root, resolution.by_ref, manifests))
    return 0


def _cmd_export_ipxact(args: argparse.Namespace) -> int:
    manifest = Manifest.from_path(Path(args.path))
    vlnv = manifest.vlnv
    output = (
        Path(args.output)
        if args.output
        else Path(f"{vlnv.vendor}.{vlnv.library}.{vlnv.name}.{vlnv.version}.xml")
    )
    output.write_text(to_ipxact(manifest, std=args.std), encoding="utf-8")
    print(f"Exported IP-XACT {args.std} for {vlnv} -> {output}")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    ref_str, at, inline = args.dependency.partition("@")
    constraint_str = args.version or (inline if at else "*")
    try:
        ref = PackageRef.parse(ref_str.strip())
        constraint = VersionConstraint.parse(constraint_str.strip())
    except HdlPackagerError as exc:
        raise ManifestError(f"Invalid dependency '{args.dependency}': {exc}") from exc

    manifest_path = Path(args.path)
    manifest = Manifest.from_path(manifest_path)  # validates and confirms it exists
    if ref == manifest.ref:
        raise ManifestError(f"A core cannot depend on itself ({ref}).")

    updated = add_dependency(manifest_path.read_text(encoding="utf-8"), ref, constraint)
    Manifest.from_str(updated)  # re-validate the edited manifest before writing
    manifest_path.write_text(updated, encoding="utf-8")
    print(f"Added {ref} = {constraint} to {manifest_path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code (0 = success)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except HdlPackagerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
