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
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .backends import CoreSource, build_eda_design, get_backend
from .cache import ContentAddressedCache, default_cache_root
from .exceptions import BackendError, HdlPackagerError, ManifestError
from .lockfile import LOCKFILE_FILENAME, Lockfile, sha256_digest
from .manifest import MANIFEST_FILENAME, Manifest
from .packaging import artifact_filename, extract_ipkg, pack_core
from .registry import LocalDirectoryRegistry, LocalRegistry, available_from_registry
from .resolver import Resolution
from .resolver import resolve as resolve_deps
from .scaffold import DEFAULT_VERSION, ScaffoldOptions, render_manifest
from .vlnv import Vlnv

# Commands that have a real implementation today. Everything else is a planned
# stub (see docs/progress_tracker.md) and reports as much instead of pretending.
_PLANNED = {
    "add": "add a dependency to ip.toml",
    "export-ipxact": "export an IP-XACT (IEEE 1685) description for tool interop",
}


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
        "--version", default=DEFAULT_VERSION, help=f"SemVer (default: {DEFAULT_VERSION})"
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
    p_install.set_defaults(func=_cmd_install)

    p_pack = sub.add_parser("pack", help="package this core into a distributable .ipkg")
    p_pack.add_argument("path", nargs="?", default=MANIFEST_FILENAME, help="path to the manifest")
    p_pack.add_argument("--output", help="output .ipkg path (default: <vlnv>.ipkg in the cwd)")
    p_pack.set_defaults(func=_cmd_pack)

    p_publish = sub.add_parser("publish", help="publish this core to a local registry")
    p_publish.add_argument(
        "path", nargs="?", default=MANIFEST_FILENAME, help="path to the manifest"
    )
    p_publish.add_argument(
        "--registry", required=True, metavar="DIR", help="registry root directory"
    )
    p_publish.set_defaults(func=_cmd_publish)

    p_pull = sub.add_parser("pull", help="download a core from a registry by VLNV")
    p_pull.add_argument("vlnv", help="the core to pull, e.g. acme:common:fifo:1.0.0")
    p_pull.add_argument("--registry", required=True, metavar="DIR", help="registry root directory")
    p_pull.add_argument("--output", metavar="DIR", help="extract the core into this directory")
    p_pull.add_argument("--cache-dir", metavar="DIR", help="cache root (default: ~/.hdlpkg/cache)")
    p_pull.set_defaults(func=_cmd_pull)

    p_yank = sub.add_parser("yank", help="hide a published version from new resolves")
    p_yank.add_argument("vlnv", help="the core version to yank, e.g. acme:common:fifo:1.0.0")
    p_yank.add_argument("--registry", required=True, metavar="DIR", help="registry root directory")
    p_yank.set_defaults(func=_cmd_yank)

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
    p_gen.set_defaults(func=_cmd_gen)

    for name, help_text in _PLANNED.items():
        p = sub.add_parser(name, help=f"[planned] {help_text}")
        p.set_defaults(func=_cmd_planned, command_name=name)

    return parser


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
    manifest_path: Path, search: list[str] | None
) -> tuple[Resolution, LocalDirectoryRegistry]:
    """Resolve *manifest_path* against a local-directory registry over *search*."""
    root = Manifest.from_path(manifest_path)
    search_dirs = search or [str(manifest_path.resolve().parent)]
    registry = LocalDirectoryRegistry([Path(d) for d in search_dirs])
    resolution = resolve_deps(root, available_from_registry(registry, root))
    return resolution, registry


def _build_lock(resolution: Resolution, registry: LocalDirectoryRegistry) -> Lockfile:
    """Build a lockfile, taking each pinned core's source/checksum from *registry*."""
    sources = {vlnv: registry.source_for(vlnv) for vlnv in resolution.vlnvs}
    checksums = {vlnv: sha256_digest(registry.artifact_bytes(vlnv)) for vlnv in resolution.vlnvs}
    return Lockfile.from_resolution(resolution, sources=sources, checksums=checksums)


def _cmd_resolve(args: argparse.Namespace) -> int:
    manifest_path = Path(args.path)
    resolution, registry = _resolve_local(manifest_path, args.search)
    lock = _build_lock(resolution, registry)
    output = Path(args.output) if args.output else manifest_path.parent / LOCKFILE_FILENAME
    output.write_text(lock.to_toml(), encoding="utf-8")

    print(f"Resolved {len(resolution.vlnvs)} package(s); wrote {output}")
    for vlnv in resolution.vlnvs:
        print(f"  {vlnv}")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    manifest_path = Path(args.path)
    resolution, registry = _resolve_local(manifest_path, args.search)
    lock = _build_lock(resolution, registry)

    cache_root = Path(args.cache_dir) if args.cache_dir else default_cache_root()
    cache = ContentAddressedCache(cache_root)
    fetched: dict[Vlnv, str] = {vlnv: registry.fetch(vlnv, cache) for vlnv in resolution.vlnvs}
    # The just-fetched digests must match what the lockfile pinned (fail closed).
    lock.verify(fetched)

    output = Path(args.output) if args.output else manifest_path.parent / LOCKFILE_FILENAME
    output.write_text(lock.to_toml(), encoding="utf-8")

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
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    manifest_path = Path(args.path)
    manifest = Manifest.from_path(manifest_path)
    registry = LocalRegistry(args.registry)
    vlnv = registry.publish_core(manifest, manifest_path.parent)
    print(f"Published {vlnv} to {args.registry}")
    return 0


def _cmd_pull(args: argparse.Namespace) -> int:
    vlnv = Vlnv.parse(args.vlnv)
    registry = LocalRegistry(args.registry)
    cache_root = Path(args.cache_dir) if args.cache_dir else default_cache_root()
    cache = ContentAddressedCache(cache_root)
    digest = registry.fetch(vlnv, cache)
    print(f"Pulled {vlnv} into {cache_root} ({digest})")
    if args.output:
        dest = extract_ipkg(cache.get(digest), Path(args.output))
        print(f"Extracted to {dest}")
    return 0


def _cmd_yank(args: argparse.Namespace) -> int:
    vlnv = Vlnv.parse(args.vlnv)
    LocalRegistry(args.registry).yank(vlnv)
    print(f"Yanked {vlnv} in {args.registry}")
    return 0


def _cmd_gen(args: argparse.Namespace) -> int:
    manifest_path = Path(args.path)
    root = Manifest.from_path(manifest_path)
    if args.target not in root.targets:
        known = ", ".join(sorted(root.targets)) or "(none)"
        raise BackendError(f"Unknown target {args.target!r}; the manifest defines: {known}.")

    resolution, registry = _resolve_local(manifest_path, args.search)
    dependencies = [
        CoreSource(manifest=registry.manifest(vlnv), root=str(registry.core_dir(vlnv)))
        for vlnv in resolution.vlnvs
    ]
    design = build_eda_design(
        CoreSource(manifest=root, root=str(manifest_path.resolve().parent)),
        args.target,
        dependencies,
    )
    outputs = get_backend(design.toolflow).generate(design)

    out_dir = Path(args.output) if args.output else Path("gen") / args.target
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, content in outputs.items():
        dest = out_dir / filename
        dest.write_text(content, encoding="utf-8")
        written.append(dest)

    print(
        f"Generated {design.toolflow} inputs for {root.vlnv} target {args.target!r} "
        f"({len(design.files)} source file(s)):"
    )
    for dest in written:
        print(f"  {dest}")
    return 0


def _cmd_planned(args: argparse.Namespace) -> int:
    name = args.command_name
    print(
        f"'hdlpkg {name}' is planned but not implemented yet: {_PLANNED[name]}.\n"
        f"See docs/progress_tracker.md for the roadmap.",
        file=sys.stderr,
    )
    return 2


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
