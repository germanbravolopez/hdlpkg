"""Core distribution: registries.

A *registry* is where IP cores live so they can be discovered, fetched, and (later)
published. Multiple backends coexist behind one :class:`Registry` interface; the
resolver and the CLI depend only on the interface, never a concrete backend.

Backends (one per registry kind):

* :class:`LocalDirectoryRegistry` -- read-only discovery by scanning local directory
  trees for ``ip.toml`` (the layout the bundled ``examples/`` use).
* :class:`LocalRegistry` -- a writable, append-only local directory store (publish /
  pull / yank).
* :class:`HttpRegistry` -- a network registry over a simple HTTP layout
  (``{base}/{vendor}/{library}/{name}/versions.json`` + ``.../{version}/{ip.toml,core.ipkg}``),
  readable and writable (``PUT``), with optional bearer-token auth.
* :class:`OciRegistry` -- a network registry over the OCI distribution v2 API, so
  cores live as OCI artifacts in any standard registry (Harbor, Artifactory, GitLab,
  Zot, ...), readable and writable, with optional bearer-token auth.

All feed :func:`available_from_registry`, which walks the dependency graph to build
the ``Mapping[PackageRef, Sequence[Manifest]]`` the resolver consumes; ``fetch``
stores the core's packed ``.ipkg`` artifact in the content-addressed cache (verifying
it). A core's "artifact" is its deterministic ``.ipkg`` (see ``packaging.py``), so its
SHA-256 is the same content address the cache keys on and the lockfile pins.

The network backends are **private by design**: a token from
``hdl_ip_packager.credentials`` (set by ``hdlpkg login``) authenticates a self-hosted
registry, so teams can share IP inside a company network without publishing publicly.
:func:`registry_from_location` is the one entry point the CLI uses -- it dispatches a
location string to the right backend by URL scheme (a bare path / ``path:`` -> local,
``http(s)://`` -> HTTP, ``oci://`` / ``oci+http://`` -> OCI) and wires in the stored
token. The Git-backed channel remains an open issue.
"""

from __future__ import annotations

import abc
import base64
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from . import __version__
from .cache import ContentAddressedCache
from .credentials import Credential, CredentialStore, registry_host
from .exceptions import HdlPackagerError, RegistryError
from .lockfile import sha256_digest
from .manifest import MANIFEST_FILENAME, Manifest
from .packaging import IPKG_SUFFIX, pack_core
from .version import OpaqueVersion, Version
from .vlnv import PackageRef, Vlnv

__all__ = [
    "GitRegistry",
    "HttpRegistry",
    "LocalDirectoryRegistry",
    "LocalRegistry",
    "OciRegistry",
    "Registry",
    "available_from_registry",
    "parse_bearer_challenge",
    "registry_from_location",
]

_IPKG_NAME = f"core{IPKG_SUFFIX}"
_YANKED_MARKER = ".yanked"


# A non-default ``User-Agent`` for every outbound request. ``urllib``'s default
# (``Python-urllib/3.x``) is rejected by common WAFs -- a JFrog Artifactory behind
# Cloudflare's Browser Integrity Check returns 403, which broke publish/pull/login in
# the trial. (``__version__`` is defined ahead of this module's import in ``__init__``.)
_USER_AGENT = f"hdlpkg/{__version__}"


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

    def publish_core(self, manifest: Manifest, core_dir: str | Path) -> Vlnv:
        """Pack and publish the core at *core_dir*; raise on a read-only backend."""
        raise RegistryError("This registry does not support publishing.")

    def yank(self, vlnv: Vlnv) -> None:
        """Hide *vlnv* from new resolves; raise on a backend that cannot yank."""
        raise RegistryError("This registry does not support yanking.")

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


_CHALLENGE_PARAM = re.compile(r'(\w+)="([^"]*)"')


def parse_bearer_challenge(header: str) -> dict[str, str] | None:
    """Parse a ``WWW-Authenticate: Bearer realm="...",service="...",scope="..."`` header.

    Returns the parameter map (at least ``realm``) for a Bearer challenge, or ``None``
    if the header is absent or not a Bearer challenge. This is the OCI/Docker
    token-exchange signal: the server tells the client where to obtain an access token.
    """
    if not header or not header.strip().lower().startswith("bearer"):
        return None
    params = dict(_CHALLENGE_PARAM.findall(header))
    return params if "realm" in params else None


def _version_token(name: str) -> Version | OpaqueVersion:
    """Parse a version directory/index name as SemVer, falling back to an opaque token.

    The registry index only carries the version *string*; the authoritative scheme
    comes from the fetched manifest. An opaque token round-trips to the same string,
    so it still addresses the right manifest/artifact regardless of the real scheme.
    """
    try:
        return Version.parse(name)
    except HdlPackagerError:
        return OpaqueVersion(name)


class HttpRegistry(Registry):
    """A network registry over a simple HTTP layout (readable + writable, token auth).

    Layout: ``{base}/{vendor}/{library}/{name}/versions.json`` (a JSON array of version
    strings) and ``{base}/{vendor}/{library}/{name}/{version}/`` holding ``ip.toml`` and
    ``core.ipkg``. Reads use ``GET``; :meth:`publish_core` uses ``PUT`` (so any
    ``PUT``-capable store -- a small service, object storage, WebDAV -- can host it).
    An optional bearer *token* (from ``hdlpkg login``) authenticates a private registry.
    """

    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": _USER_AGENT}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(request) as response:
                data: bytes = response.read()
                return data
        except (urllib.error.URLError, OSError) as exc:
            raise RegistryError(f"HTTP registry request failed for {url}: {exc}") from exc

    def _put(self, url: str, data: bytes, content_type: str) -> None:
        headers = {**self._headers(), "Content-Type": content_type}
        request = urllib.request.Request(url, data=data, headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(request):
                return
        except (urllib.error.URLError, OSError) as exc:
            raise RegistryError(f"HTTP registry PUT failed for {url}: {exc}") from exc

    def _package_url(self, ref: PackageRef) -> str:
        return f"{self.base_url}/{ref.vendor}/{ref.library}/{ref.name}"

    def _core_url(self, vlnv: Vlnv) -> str:
        return f"{self._package_url(vlnv.ref)}/{vlnv.version}"

    def versions(self, ref: PackageRef) -> list[Vlnv]:
        url = f"{self._package_url(ref)}/versions.json"
        try:
            raw = self._get(url)
        except RegistryError:
            return []  # an unknown package is "no versions", not an error
        try:
            names = json.loads(raw)
            return [ref.with_version(_version_token(str(name))) for name in names]
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

    def publish_core(self, manifest: Manifest, core_dir: str | Path) -> Vlnv:
        """Upload the core (append-only): refuse if its version is already indexed."""
        vlnv = manifest.vlnv
        names = [str(existing.version) for existing in self.versions(vlnv.ref)]
        if str(vlnv.version) in names:
            raise RegistryError(f"{vlnv} is already published (registries are append-only).")
        manifest_bytes = (Path(core_dir) / MANIFEST_FILENAME).read_bytes()
        self._put(f"{self._core_url(vlnv)}/{MANIFEST_FILENAME}", manifest_bytes, "application/toml")
        self._put(
            f"{self._core_url(vlnv)}/{_IPKG_NAME}",
            pack_core(manifest, core_dir),
            "application/octet-stream",
        )
        updated = sorted([*names, str(vlnv.version)])
        self._put(
            f"{self._package_url(vlnv.ref)}/versions.json",
            json.dumps(updated).encode("utf-8"),
            "application/json",
        )
        return vlnv

    def source_for(self, vlnv: Vlnv) -> str:
        """The lockfile ``source`` for *vlnv*: a reference to this HTTP registry."""
        return f"registry:{self.base_url}"


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
                # A non-SemVer directory name belongs to an opaque-scheme core; read
                # its manifest to recover the opaque version (the dir is named after it).
                manifest_path = entry / MANIFEST_FILENAME
                if manifest_path.is_file():
                    try:
                        found.append(Manifest.from_path(manifest_path).vlnv)
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


_OCI_MANIFEST_TYPE = "application/vnd.oci.image.manifest.v1+json"
_OCI_CONFIG_TYPE = "application/vnd.hdlpkg.core.config.v1+toml"
_OCI_LAYER_TYPE = "application/vnd.hdlpkg.ipkg.v1.tar+gzip"
_OCI_ARTIFACT_TYPE = "application/vnd.hdlpkg.core.v1"


class OciRegistry(Registry):
    """A network registry over the OCI distribution v2 API (readable + writable).

    Cores are stored as OCI artifacts in any standard registry (Harbor, Artifactory,
    Nexus, GitLab, Zot, ECR/ACR, ...): a core's ``ip.toml`` is the artifact *config*
    blob and its packed ``.ipkg`` is the single *layer*, tagged with the version. The
    package maps to the repository ``{prefix}/{vendor}/{library}/{name}``. An optional
    bearer *token* (from ``hdlpkg login``) authenticates a private registry.

    Transport: ``oci://host/prefix`` uses HTTPS (the norm); ``oci+http://host/prefix``
    uses plaintext HTTP (for an internal/dev registry without TLS, and the test server).
    """

    def __init__(self, location: str, credential: Credential | None = None) -> None:
        scheme, _, rest = location.partition("://")
        self.transport = "http" if scheme.lower() == "oci+http" else "https"
        split = urlsplit(f"{self.transport}://{rest}")
        if not split.netloc:
            raise RegistryError(f"OCI registry location has no host: {location!r}")
        self.host = split.netloc
        self.prefix = split.path.strip("/")
        self.credential = credential
        self._access_token: str | None = None  # cached from a token-exchange (per scope)

    def _base(self) -> str:
        return f"{self.transport}://{self.host}"

    def _repo(self, ref: PackageRef) -> str:
        parts = [p for p in (self.prefix, ref.vendor, ref.library, ref.name) if p]
        return "/".join(parts).lower()

    def _bearer(self) -> str | None:
        """The bearer to send up front: a cached exchanged token, else a direct token.

        A username-less credential is a ready-to-use bearer (the self-hosted case); a
        username+secret credential is meant for the realm exchange, so it is *not* sent
        directly -- the first request goes unauthenticated and the 401 challenge drives
        the exchange.
        """
        if self._access_token:
            return self._access_token
        if self.credential and not self.credential.is_basic:
            return self.credential.secret
        return None

    def _headers(
        self, accept: str | None = None, content_type: str | None = None
    ) -> dict[str, str]:
        headers: dict[str, str] = {"User-Agent": _USER_AGENT}
        bearer = self._bearer()
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        if accept:
            headers["Accept"] = accept
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _send(
        self,
        method: str,
        url: str,
        data: bytes | None = None,
        accept: str | None = None,
        content_type: str | None = None,
        _retried: bool = False,
    ) -> tuple[int, object, bytes]:
        """Send a request, returning (status, headers, body); raise only on transport errors.

        An HTTP error status is returned (not raised) so callers can branch on it (a 404
        is "absent", not a failure; a 200 on a HEAD means "blob already there"). On a
        ``401`` carrying a Bearer challenge, perform the OCI token exchange once and retry
        (this also upgrades a pull-scoped token to a push scope when publishing).
        """
        request = urllib.request.Request(
            url, data=data, headers=self._headers(accept, content_type), method=method
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and not _retried:
                challenge = parse_bearer_challenge(exc.headers.get("WWW-Authenticate", ""))
                if challenge and self._exchange_token(challenge):
                    return self._send(method, url, data, accept, content_type, _retried=True)
            return exc.code, exc.headers, exc.read()
        except (urllib.error.URLError, OSError) as exc:
            raise RegistryError(f"OCI request {method} {url} failed: {exc}") from exc

    def _exchange_token(self, challenge: dict[str, str]) -> bool:
        """Exchange credentials at the challenge's ``realm`` for an access token (cached).

        Authenticates to the token endpoint with HTTP Basic when a credential is present
        (else anonymously, for public pull tokens), passing the server-supplied
        ``service``/``scope`` so the issued token carries exactly the rights requested.
        Returns True if a token was obtained.
        """
        realm = challenge["realm"]
        params = {k: challenge[k] for k in ("service", "scope") if challenge.get(k)}
        url = f"{realm}?{urlencode(params)}" if params else realm
        headers: dict[str, str] = {"User-Agent": _USER_AGENT}
        if self.credential:
            raw = f"{self.credential.username or ''}:{self.credential.secret}".encode()
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as response:
                payload = json.loads(response.read())
        except (urllib.error.URLError, OSError, ValueError):  # ValueError: bad realm URL / JSON
            return False
        token = payload.get("token") or payload.get("access_token")
        if isinstance(token, str) and token:
            self._access_token = token
            return True
        return False

    def _image_manifest(self, vlnv: Vlnv) -> dict[str, object]:
        url = f"{self._base()}/v2/{self._repo(vlnv.ref)}/manifests/{vlnv.version}"
        status, _, body = self._send("GET", url, accept=_OCI_MANIFEST_TYPE)
        if status != 200:
            raise RegistryError(f"{vlnv} is not in OCI registry {self.host} (HTTP {status}).")
        try:
            manifest: dict[str, object] = json.loads(body)
            return manifest
        except json.JSONDecodeError as exc:
            raise RegistryError(f"Malformed OCI manifest for {vlnv}: {exc}") from exc

    def _blob(self, repo: str, digest: str) -> bytes:
        status, _, body = self._send("GET", f"{self._base()}/v2/{repo}/blobs/{digest}")
        if status != 200:
            raise RegistryError(f"OCI blob {digest} missing in {repo} (HTTP {status}).")
        return body

    def versions(self, ref: PackageRef) -> list[Vlnv]:
        status, _, body = self._send("GET", f"{self._base()}/v2/{self._repo(ref)}/tags/list")
        if status == 404:
            return []  # repository unknown -> no versions
        if status != 200:
            raise RegistryError(f"OCI tags request for {self._repo(ref)} failed (HTTP {status}).")
        try:
            tags = json.loads(body).get("tags") or []
        except (json.JSONDecodeError, AttributeError) as exc:
            raise RegistryError(f"Malformed OCI tag list for {self._repo(ref)}: {exc}") from exc
        return [ref.with_version(_version_token(str(tag))) for tag in tags]

    def manifest(self, vlnv: Vlnv) -> Manifest:
        config = self._image_manifest(vlnv).get("config")
        if not isinstance(config, dict) or "digest" not in config:
            raise RegistryError(f"OCI manifest for {vlnv} has no config descriptor.")
        raw = self._blob(self._repo(vlnv.ref), str(config["digest"]))
        try:
            return Manifest.from_str(raw.decode("utf-8"))
        except (UnicodeDecodeError, HdlPackagerError) as exc:
            raise RegistryError(f"Invalid manifest for {vlnv}: {exc}") from exc

    def artifact_bytes(self, vlnv: Vlnv) -> bytes:
        layers = self._image_manifest(vlnv).get("layers")
        if not isinstance(layers, list) or not layers:
            raise RegistryError(f"OCI manifest for {vlnv} has no layer.")
        return self._blob(self._repo(vlnv.ref), str(layers[0]["digest"]))

    def _push_blob(self, repo: str, data: bytes) -> dict[str, object]:
        """Upload *data* as a blob (skipping if already present); return its descriptor."""
        digest = sha256_digest(data)
        present, _, _ = self._send("HEAD", f"{self._base()}/v2/{repo}/blobs/{digest}")
        if present != 200:
            status, headers, _ = self._send("POST", f"{self._base()}/v2/{repo}/blobs/uploads/")
            if status not in (201, 202):
                raise RegistryError(f"OCI upload start failed for {repo} (HTTP {status}).")
            location = headers.get("Location")  # type: ignore[attr-defined]
            if not location:
                raise RegistryError(f"OCI upload for {repo} returned no Location header.")
            upload = location if "://" in location else f"{self._base()}{location}"
            separator = "&" if "?" in upload else "?"
            status, _, _ = self._send(
                "PUT",
                f"{upload}{separator}digest={digest}",
                data=data,
                content_type="application/octet-stream",
            )
            if status != 201:
                raise RegistryError(f"OCI blob upload failed for {repo} (HTTP {status}).")
        return {"digest": digest, "size": len(data)}

    def publish_core(self, manifest: Manifest, core_dir: str | Path) -> Vlnv:
        """Push the core as an OCI artifact (append-only): refuse to overwrite a tag."""
        vlnv = manifest.vlnv
        repo = self._repo(vlnv.ref)
        url = f"{self._base()}/v2/{repo}/manifests/{vlnv.version}"
        if self._send("GET", url, accept=_OCI_MANIFEST_TYPE)[0] == 200:
            raise RegistryError(f"{vlnv} is already published (registries are append-only).")
        config = self._push_blob(repo, (Path(core_dir) / MANIFEST_FILENAME).read_bytes())
        config["mediaType"] = _OCI_CONFIG_TYPE
        layer = self._push_blob(repo, pack_core(manifest, core_dir))
        layer["mediaType"] = _OCI_LAYER_TYPE
        image = {
            "schemaVersion": 2,
            "mediaType": _OCI_MANIFEST_TYPE,
            "artifactType": _OCI_ARTIFACT_TYPE,
            "config": config,
            "layers": [layer],
        }
        body = json.dumps(image, sort_keys=True).encode("utf-8")
        status, _, _ = self._send("PUT", url, data=body, content_type=_OCI_MANIFEST_TYPE)
        if status != 201:
            raise RegistryError(f"OCI manifest publish failed for {vlnv} (HTTP {status}).")
        return vlnv

    def source_for(self, vlnv: Vlnv) -> str:
        """The lockfile ``source`` for *vlnv*: the OCI artifact reference."""
        return f"oci:{self.host}/{self._repo(vlnv.ref)}:{vlnv.version}"


def default_git_cache_root() -> Path:
    """Where Git-backed registry clones are kept (separate from the artifact cache).

    Overridable with ``HDLPKG_GIT_CACHE`` (so a clone never lands in the user's real home
    during tests/CI).
    """
    override = os.environ.get("HDLPKG_GIT_CACHE")
    return Path(override) if override else Path.home() / ".hdlpkg" / "git"


def _parse_git_location(location: str) -> tuple[str, str | None]:
    """Split a ``git+<url>[@<ref>]`` location into the git URL and an optional ref.

    The ``git+`` prefix is stripped to recover the real URL. An optional ``@<ref>`` (a
    branch, tag, or commit) is taken from the *final* path segment only, so an ``ssh``
    user (``git@host``) earlier in the URL is never mistaken for a ref.
    """
    url = location[len("git+") :]
    head, _, tail = url.rpartition("/")
    name, at, ref = tail.partition("@")
    if at:
        return f"{head}/{name}", ref
    return url, None


class GitRegistry(Registry):
    """A registry backed by a Git repository of cores (a new ``git+...`` location).

    The repo is cloned (or updated) into a local cache and checked out at the requested
    ref (default: the remote's default branch); discovery then mirrors
    :class:`LocalDirectoryRegistry` over the working tree. The lockfile ``source`` binds
    each pinned core to the exact commit (``git+<url>@<sha>``), so a VLNV/version is
    traceable to immutable source. Authentication is delegated to the user's own git
    configuration. The ``git`` CLI must be installed.
    """

    def __init__(self, location: str, *, cache_root: Path | None = None) -> None:
        self.location = location
        self.url, self.ref = _parse_git_location(location)
        work = self._sync(cache_root or default_git_cache_root())
        self.commit = self._git("rev-parse", "HEAD", cwd=work)
        self._inner = LocalDirectoryRegistry([work])

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        """Run a git command, returning trimmed stdout; raise :class:`RegistryError`."""
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # never block on a credential prompt
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
            )
        except OSError as exc:  # git not installed
            raise RegistryError(f"git is required for a git+ registry: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RegistryError(f"git {' '.join(args)} failed for {self.url}: {detail}")
        return result.stdout.strip()

    def _sync(self, cache_root: Path) -> Path:
        """Clone (or fetch) the repo into the cache and check out the target commit."""
        cache_root.mkdir(parents=True, exist_ok=True)
        work = cache_root / hashlib.sha256(self.location.encode()).hexdigest()[:16]
        if (work / ".git").is_dir():
            self._git("fetch", "--tags", "--force", "--prune", "origin", cwd=work)
        else:
            self._git("clone", "--quiet", self.url, str(work))
        target = self.ref or self._default_branch(work)
        self._git("checkout", "--quiet", "--force", self._resolve(work, target), cwd=work)
        return work

    def _default_branch(self, work: Path) -> str:
        """The remote's default branch name (e.g. ``main``)."""
        return self._git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=work).rsplit(
            "/", 1
        )[-1]

    def _resolve(self, work: Path, ref: str) -> str:
        """Resolve *ref* to a commit SHA, preferring the remote branch over a tag/SHA."""
        for candidate in (f"origin/{ref}", ref):
            try:
                return self._git("rev-parse", "--verify", f"{candidate}^{{commit}}", cwd=work)
            except RegistryError:
                continue  # not this kind of ref; try the next interpretation
        raise RegistryError(f"git ref {ref!r} not found in {self.url}")

    def versions(self, ref: PackageRef) -> list[Vlnv]:
        return self._inner.versions(ref)

    def manifest(self, vlnv: Vlnv) -> Manifest:
        return self._inner.manifest(vlnv)

    def artifact_bytes(self, vlnv: Vlnv) -> bytes:
        return self._inner.artifact_bytes(vlnv)

    def source_for(self, vlnv: Vlnv) -> str:
        """Provenance binding the core to an immutable commit: ``git+<url>@<sha>``."""
        self._inner._path(vlnv)  # raise if the core is not in this registry
        return f"git+{self.url}@{self.commit}"


def registry_from_location(
    location: str, *, credentials: CredentialStore | None = None
) -> Registry:
    """Build the right registry backend for *location*, dispatched by URL scheme.

    ``http(s)://`` -> :class:`HttpRegistry`, ``oci://`` / ``oci+http://`` ->
    :class:`OciRegistry`, ``git+...://`` -> :class:`GitRegistry`, and a bare path /
    ``path:<dir>`` / ``file://<dir>`` -> :class:`LocalRegistry`. For a network location the
    credential for its host is read from *credentials* (if given): HTTP uses the secret as a
    direct bearer; OCI uses the full credential (so a username+secret drives the token
    exchange); Git authenticates through the user's own git configuration (ssh keys /
    credential helpers), so the credential store is not consulted. Raises
    :class:`RegistryError` on an unknown scheme. This is the one place the CLI selects a backend.
    """
    head, separator, rest = location.partition("://")
    scheme = head.lower() if separator else ""
    if not separator:
        prefix, colon, tail = location.partition(":")
        if colon and prefix.lower() == "path":
            return LocalRegistry(tail)
        return LocalRegistry(location)  # bare path (incl. a Windows drive like C:\...)
    if scheme.startswith("git+"):
        return GitRegistry(location)
    if scheme == "file":
        return LocalRegistry(rest)
    credential = credentials.credential_for(registry_host(location)) if credentials else None
    if scheme in ("http", "https"):
        return HttpRegistry(location, token=credential.secret if credential else None)
    if scheme in ("oci", "oci+http"):
        return OciRegistry(location, credential=credential)
    raise RegistryError(f"Unsupported registry location scheme {scheme!r}: {location!r}")


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
