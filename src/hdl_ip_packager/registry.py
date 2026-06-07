"""Core distribution: registries.

A *registry* is where IP cores live so they can be discovered, fetched, and (later)
published. Multiple backends coexist behind one :class:`Registry` interface; the
resolver and the CLI depend only on the interface, never a concrete backend.

Implemented backends:

* :class:`LocalDirectoryRegistry` -- cores discovered by scanning local directory
  trees for ``ip.toml`` (the layout the bundled ``examples/`` use).
* :class:`HttpRegistry` -- cores served by a static HTTP index with the layout
  ``{base}/{vendor}/{library}/{name}/versions.json`` and
  ``{base}/{vendor}/{library}/{name}/{version}/ip.toml``.

Both feed :func:`available_from_registry`, which walks the dependency graph to
build the ``Mapping[PackageRef, Sequence[Manifest]]`` the resolver consumes, and
``fetch`` stores the core's artifact in the content-addressed cache (verifying it).

At this milestone a core's "artifact" is its manifest bytes -- enough to exercise
discover -> resolve -> fetch -> verify end to end. Packaging (M5) replaces the
artifact with the packed core without changing this interface. The Git and OCI
backends are tracked as open issues (they need external tooling/live services to
implement and test); the design intent is in ``docs/architecture.md``.
"""

from __future__ import annotations

import abc
import json
import urllib.error
import urllib.request
from pathlib import Path

from .cache import ContentAddressedCache
from .exceptions import HdlPackagerError, RegistryError
from .manifest import MANIFEST_FILENAME, Manifest
from .packaging import IPKG_SUFFIX, pack_core
from .version import Version
from .vlnv import PackageRef, Vlnv

__all__ = [
    "HttpRegistry",
    "LocalDirectoryRegistry",
    "LocalRegistry",
    "Registry",
    "available_from_registry",
]

_IPKG_NAME = f"core{IPKG_SUFFIX}"
_YANKED_MARKER = ".yanked"


class Registry(abc.ABC):
    """Abstract source of IP cores (one concrete backend per registry kind)."""

    @abc.abstractmethod
    def versions(self, ref: PackageRef) -> list[Vlnv]:
        """Return every available version of *ref* (empty if the package is unknown)."""

    @abc.abstractmethod
    def manifest(self, vlnv: Vlnv) -> Manifest:
        """Return the parsed manifest of *vlnv*; raise :class:`RegistryError` if absent."""

    @abc.abstractmethod
    def artifact_bytes(self, vlnv: Vlnv) -> bytes:
        """Return the raw artifact bytes for *vlnv* (the manifest, until packaging lands)."""

    def fetch(self, vlnv: Vlnv, cache: ContentAddressedCache) -> str:
        """Fetch *vlnv*'s artifact, store it in *cache*, and return its digest."""
        return cache.put(self.artifact_bytes(vlnv))

    def publish(self, artifact_path: str) -> Vlnv:
        """Publish a packaged artifact (overridden by writable backends in M5)."""
        raise RegistryError("This registry does not support publishing.")

    def source_for(self, vlnv: Vlnv) -> str:
        """A lockfile ``source`` string describing where *vlnv* came from (best effort)."""
        return ""


def _display_path(path: Path) -> str:
    """A forward-slash path relative to the cwd when possible, else absolute."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return resolved.as_posix()


class LocalDirectoryRegistry(Registry):
    """A registry backed by local directory trees of cores (each a dir with ``ip.toml``)."""

    def __init__(self, roots: list[Path]) -> None:
        self._paths: dict[Vlnv, Path] = {}
        self._by_ref: dict[PackageRef, list[Vlnv]] = {}
        for root in roots:
            if not Path(root).is_dir():
                continue
            for path in sorted(Path(root).rglob(MANIFEST_FILENAME)):
                try:
                    manifest = Manifest.from_path(path)
                except HdlPackagerError:
                    continue  # a search tree may hold non-core or invalid TOML
                if manifest.vlnv in self._paths:
                    continue  # first occurrence wins (deterministic via sorted scan)
                self._paths[manifest.vlnv] = path
                self._by_ref.setdefault(manifest.ref, []).append(manifest.vlnv)

    def versions(self, ref: PackageRef) -> list[Vlnv]:
        return list(self._by_ref.get(ref, []))

    def _path(self, vlnv: Vlnv) -> Path:
        path = self._paths.get(vlnv)
        if path is None:
            raise RegistryError(f"{vlnv} is not in the local registry.")
        return path

    def manifest(self, vlnv: Vlnv) -> Manifest:
        return Manifest.from_path(self._path(vlnv))

    def artifact_bytes(self, vlnv: Vlnv) -> bytes:
        path = self._path(vlnv)
        return pack_core(Manifest.from_path(path), path.parent)

    def source_for(self, vlnv: Vlnv) -> str:
        """The lockfile ``source`` string for *vlnv* (a local path reference)."""
        return f"path:{_display_path(self._path(vlnv).parent)}"

    def core_dir(self, vlnv: Vlnv) -> Path:
        """The on-disk directory holding *vlnv*'s ``ip.toml`` (and its sources)."""
        return self._path(vlnv).parent


class HttpRegistry(Registry):
    """A registry served by a static HTTP index (read-only)."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _get(self, url: str) -> bytes:
        try:
            with urllib.request.urlopen(url) as response:
                data: bytes = response.read()
                return data
        except (urllib.error.URLError, OSError) as exc:
            raise RegistryError(f"HTTP registry request failed for {url}: {exc}") from exc

    def _core_url(self, vlnv: Vlnv) -> str:
        return f"{self.base_url}/{vlnv.vendor}/{vlnv.library}/{vlnv.name}/{vlnv.version}"

    def versions(self, ref: PackageRef) -> list[Vlnv]:
        url = f"{self.base_url}/{ref.vendor}/{ref.library}/{ref.name}/versions.json"
        try:
            raw = self._get(url)
        except RegistryError:
            return []  # an unknown package is "no versions", not an error
        try:
            names = json.loads(raw)
            return [ref.with_version(Version.parse(str(name))) for name in names]
        except (json.JSONDecodeError, HdlPackagerError) as exc:
            raise RegistryError(f"Malformed versions index at {url}: {exc}") from exc

    def manifest(self, vlnv: Vlnv) -> Manifest:
        raw = self._get(f"{self._core_url(vlnv)}/{MANIFEST_FILENAME}")
        try:
            return Manifest.from_str(raw.decode("utf-8"))
        except (UnicodeDecodeError, HdlPackagerError) as exc:
            raise RegistryError(f"Invalid manifest for {vlnv}: {exc}") from exc

    def artifact_bytes(self, vlnv: Vlnv) -> bytes:
        return self._get(f"{self._core_url(vlnv)}/{_IPKG_NAME}")


class LocalRegistry(Registry):
    """A writable local registry with a structured, append-only on-disk layout.

    Layout: ``<root>/<vendor>/<library>/<name>/<version>/`` holding ``ip.toml`` and
    ``core.ipkg``; a ``.yanked`` marker hides a version from new resolves without
    deleting it (so existing lockfiles still verify). Publishing is **append-only**:
    re-publishing an existing version is refused.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _dir(self, vlnv: Vlnv) -> Path:
        return self.root / vlnv.vendor / vlnv.library / vlnv.name / str(vlnv.version)

    def versions(self, ref: PackageRef) -> list[Vlnv]:
        base = self.root / ref.vendor / ref.library / ref.name
        if not base.is_dir():
            return []
        found: list[Vlnv] = []
        for entry in sorted(base.iterdir()):
            if not entry.is_dir() or (entry / _YANKED_MARKER).exists():
                continue
            try:
                found.append(ref.with_version(Version.parse(entry.name)))
            except HdlPackagerError:
                continue
        return found

    def manifest(self, vlnv: Vlnv) -> Manifest:
        path = self._dir(vlnv) / MANIFEST_FILENAME
        if not path.is_file():
            raise RegistryError(f"{vlnv} is not in registry {self.root}.")
        return Manifest.from_path(path)

    def artifact_bytes(self, vlnv: Vlnv) -> bytes:
        path = self._dir(vlnv) / _IPKG_NAME
        try:
            return path.read_bytes()
        except OSError as exc:
            raise RegistryError(f"{vlnv} artifact is not in registry {self.root}: {exc}") from exc

    def publish_core(self, manifest: Manifest, core_dir: str | Path) -> Vlnv:
        """Pack the core at *core_dir* and publish it; refuse to overwrite a version."""
        vlnv = manifest.vlnv
        dest = self._dir(vlnv)
        if dest.exists():
            raise RegistryError(f"{vlnv} is already published (registries are append-only).")
        dest.mkdir(parents=True)
        (dest / MANIFEST_FILENAME).write_bytes((Path(core_dir) / MANIFEST_FILENAME).read_bytes())
        (dest / _IPKG_NAME).write_bytes(pack_core(manifest, core_dir))
        return vlnv

    def yank(self, vlnv: Vlnv) -> None:
        """Hide *vlnv* from new resolves (idempotent); raise if it was never published."""
        dest = self._dir(vlnv)
        if not dest.is_dir():
            raise RegistryError(f"Cannot yank {vlnv}: it is not published in {self.root}.")
        (dest / _YANKED_MARKER).touch()

    def source_for(self, vlnv: Vlnv) -> str:
        """The lockfile ``source`` for *vlnv*: a reference to this published registry."""
        return f"registry:{_display_path(self.root)}"


def available_from_registry(registry: Registry, root: Manifest) -> dict[PackageRef, list[Manifest]]:
    """Walk *root*'s dependency graph in *registry*, collecting candidate manifests.

    Returns the ``Mapping[PackageRef, Sequence[Manifest]]`` the resolver consumes:
    for every package reachable from the root's dependencies, the manifests of all
    versions the registry offers.
    """
    index: dict[PackageRef, list[Manifest]] = {}
    seen: set[PackageRef] = set()
    queue: list[PackageRef] = [dep.ref for dep in root.dependencies]
    while queue:
        ref = queue.pop()
        if ref in seen:
            continue
        seen.add(ref)
        manifests = [registry.manifest(vlnv) for vlnv in registry.versions(ref)]
        index[ref] = manifests
        for manifest in manifests:
            queue.extend(dep.ref for dep in manifest.dependencies)
    return index
