# Registry — `registry.py`

Where IP cores live so they can be discovered, fetched, and published. Multiple
backends coexist behind one `Registry` interface; the resolver and CLI depend only on
the interface, never a concrete backend.

- **Source**: [src/hdl_ip_packager/registry.py](../../src/hdl_ip_packager/registry.py)
- **Import**: `from hdl_ip_packager import Registry, LocalDirectoryRegistry, HttpRegistry, LocalRegistry, available_from_registry`

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

### `HttpRegistry(base_url)`
A read-only registry served by a **static HTTP index**:

```
{base}/{vendor}/{library}/{name}/versions.json     # JSON array of versions
{base}/{vendor}/{library}/{name}/{version}/ip.toml
{base}/{vendor}/{library}/{name}/{version}/core.ipkg
```

Fetched with the stdlib `urllib`. An unknown package is treated as "no versions" (not
an error); a malformed index or manifest raises `RegistryError`.

### `LocalRegistry(root)` — writable
A writable registry with a structured, **append-only** on-disk layout:
`<root>/<vendor>/<library>/<name>/<version>/` holding `ip.toml` + `core.ipkg`.

| Method | Description |
|--------|-------------|
| `publish_core(manifest, core_dir) -> Vlnv` | Pack the core and publish it; **refuses to overwrite** an existing version (append-only). |
| `yank(vlnv)` | Drop a `.yanked` marker that hides the version from new resolves without breaking existing lockfiles. Idempotent; raises if never published. |
| `versions` / `manifest` / `artifact_bytes` | As per the interface; `versions` skips yanked entries. |

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

## Deferred backends

**Git-backed** and **OCI artifact** registries are designed but not implemented —
both need external tooling / a live service to build and test honestly (tracked as
open issues). The interface above does not change when they land.

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
