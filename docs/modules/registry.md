# Registry — `registry.py`

Where IP cores live so they can be discovered, fetched, and published. Multiple
backends coexist behind one `Registry` interface; the resolver and CLI depend only on
the interface, never a concrete backend.

- **Source**: [src/hdl_ip_packager/registry.py](../../src/hdl_ip_packager/registry.py)
- **Import**: `from hdl_ip_packager import Registry, LocalDirectoryRegistry, HttpRegistry, LocalRegistry, OciRegistry, registry_from_location, available_from_registry`

## Selecting a backend: `registry_from_location`

```python
def registry_from_location(location: str, *, credentials: CredentialStore | None = None) -> Registry
```

The single entry point the CLI uses. It dispatches a `--registry` location to a backend
by URL scheme and wires in the stored bearer token for the location's host:

| Location | Backend |
|----------|---------|
| a bare path, `path:<dir>`, `file://<dir>` | `LocalRegistry` (writable local dir) |
| `http://...` / `https://...` | `HttpRegistry` |
| `oci://...` (HTTPS) / `oci+http://...` (plaintext) | `OciRegistry` |

An unknown scheme raises `RegistryError`. A Windows drive (`C:\...`) is treated as a
path, not a scheme. Because every command routes through this one factory, the rest of
the CLI is backend-agnostic and the registry protocol surface stays stable.

## The `Registry` interface

An abstract base every backend implements:

| Method | Description |
|--------|-------------|
| `versions(ref: PackageRef) -> list[Vlnv]` | Every available version of a package (empty if unknown). |
| `manifest(vlnv: Vlnv) -> Manifest` | The parsed manifest of one version. Raises `RegistryError` if absent. |
| `artifact_bytes(vlnv: Vlnv) -> bytes` | The core's packed [`.ipkg`](packaging.md) bytes. |
| `fetch(vlnv, cache) -> str` | Store the artifact in a [content-addressed cache](cache.md) and return its digest. |
| `publish(...)` | Overridden by writable backends; the default raises `RegistryError`. |

## Backends

### `LocalDirectoryRegistry([roots])`
Discovers cores by scanning local directory trees for `ip.toml` (the layout the
bundled `examples/` use). First occurrence wins on a deterministic sorted scan;
invalid/non-core TOML is skipped. Extra helpers: `source_for(vlnv)` (the lockfile
`path:` reference) and `core_dir(vlnv)` (the on-disk directory of a core — used by
[`gen`](backends.md)). This backs `hdlpkg resolve`/`install`/`gen`/`tree`.

### `HttpRegistry(base_url, token=None)` — writable, authenticated
A network registry over a simple HTTP layout:

```
{base}/{vendor}/{library}/{name}/versions.json     # JSON array of versions
{base}/{vendor}/{library}/{name}/{version}/ip.toml
{base}/{vendor}/{library}/{name}/{version}/core.ipkg
```

Reads via `GET`; `publish_core` writes via `PUT` (so any `PUT`-capable store — a small
service, object storage, WebDAV — can host it), append-only. An optional bearer `token`
authenticates a private registry. An unknown package is "no versions" (not an error); a
malformed index/manifest or a failed request raises `RegistryError`.

#### What "OCI" is, in plain terms

**OCI = Open Container Initiative.** An *OCI registry* is the same kind of server that
stores Docker images — products like Harbor, GitLab Container Registry, JFrog
Artifactory, Sonatype Nexus, AWS ECR, Azure ACR, GitHub Packages, and the lightweight
open-source Zot / CNCF distribution. An *OCI artifact* just means storing something other
than a Docker image (here: your packed `.ipkg` core) as content-addressed blobs in one of
those servers, using their standard push/pull HTTP API.

The key thing that resolves the common worry: **"publish" does not mean "publish to the
public internet."** It means "push to a registry server," and that server is whatever you
point it at. Three crucial properties:

- **Private by default, with authentication.** Access requires a login/token; nobody
  outside gets in.
- **Self-hostable.** You run Harbor / Zot / Artifactory on your own servers inside the
  company LAN. Nothing is exposed to the internet.
- **Built for exactly this scenario** — different teams/projects pulling shared artifacts
  from a central internal registry, with per-team access control.

So choosing OCI and keeping your IP private are the *same* goal, not opposite ones:
`hdlpkg` speaks the OCI protocol, and you decide whether the registry it talks to is an
internal Harbor box or a managed cloud one.

### `OciRegistry(location, token=None)` — writable, authenticated
A network registry over the **OCI distribution v2 API**, so cores live as OCI artifacts
in any standard registry (Harbor, Artifactory, Nexus, GitLab, Zot, ECR/ACR) — all
self-hostable and private by default. A core's `ip.toml` is the artifact *config* blob
and its `.ipkg` is the single *layer*, tagged with the version; the package maps to
repository `{prefix}/{vendor}/{library}/{name}`. Implements blob upload (HEAD-skip +
POST/PUT), manifest/tag PUT+GET, and `tags/list`; publishing is append-only. `oci://`
uses HTTPS, `oci+http://` plaintext (internal/dev). Because the layer *is* the `.ipkg`,
its OCI digest is the same content address the cache and lockfile pin.

### `LocalRegistry(root)` — writable
A writable registry with a structured, **append-only** on-disk layout:
`<root>/<vendor>/<library>/<name>/<version>/` holding `ip.toml` + `core.ipkg`.

| Method | Description |
|--------|-------------|
| `publish_core(manifest, core_dir) -> Vlnv` | Pack the core and publish it; **refuses to overwrite** an existing version (append-only). |
| `yank(vlnv)` | Drop a `.yanked` marker that hides the version from new resolves without breaking existing lockfiles. Idempotent; raises if never published. |
| `versions` / `manifest` / `artifact_bytes` | As per the interface; `versions` skips yanked entries. A non-SemVer ([`opaque`](versioning.md)) version directory is recovered by reading its `ip.toml`, so opaque cores resolve from a published registry too. |

This backs `hdlpkg publish`/`pull`/`yank`, and — via `resolve`/`install`/`tree
--registry DIR` — is also a **read** source you can resolve and install directly
from (not just `pull` by VLNV).

## Building the resolver's input

```python
def available_from_registry(registry: Registry, root: Manifest) -> dict[PackageRef, list[Manifest]]
```

Walks the root's dependency graph in the registry, collecting the manifests of every
reachable package's versions — exactly the `available` map [`resolve`](resolver.md)
consumes.

## Private registries: authentication

The network backends are private by design. A per-host bearer token from
[credentials.py](credentials.md) (set by `hdlpkg login`) is sent as
`Authorization: Bearer <token>` on every request, so a team publishes to and consumes
from an internal registry without the cores ever being public. `registry_from_location`
reads the token automatically; missing/wrong credentials fail closed.

## Deferred backends

A **Git-backed** registry channel is still designed but not implemented (it needs `git`
+ a live remote to test honestly). The OCI **token-exchange** auth flow (the Docker
`WWW-Authenticate` realm dance some managed registries require) is a tracked refinement —
today the stored token is presented directly as a bearer credential, which self-hosted
registries can accept. The interface above does not change when these land.

## Errors

`RegistryError` — a missing core, a malformed index, a failed HTTP request, or a
re-publish of an existing version.

## Example

```python
from pathlib import Path
from hdl_ip_packager import LocalRegistry, ContentAddressedCache, Vlnv

reg = LocalRegistry("registry/")
reg.publish_core(Manifest.from_path("examples/fifo/ip.toml"), "examples/fifo")
digest = reg.fetch(Vlnv.parse("acme:common:fifo:1.0.0"), ContentAddressedCache(Path(".cache")))
```
