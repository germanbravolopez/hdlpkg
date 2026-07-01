# Identity (VLNV) — `vlnv.py`

How an IP core is named. Pure module (parsing/formatting only).

- **Source**: [src/hdlpkg/vlnv.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/vlnv.py)
- **Import**: `from hdlpkg import PackageRef, Vlnv`

## Purpose

Cores are named with **VLNV** — **V**endor : **L**ibrary : **N**ame : **V**ersion —
the identity scheme from the IP-XACT standard (IEEE 1685) and FuseSoC. A globally
meaningful, collision-resistant name, e.g. `acme:comm:uart:1.2.0`.

Two value types separate the two uses of a name:

- `PackageRef` — the version-*less* `vendor:library:name` triple, used as a
  dependency **key** (the version comes from a separate [constraint](versioning.md)).
- `Vlnv` — a fully-qualified `vendor:library:name:version` identifying one concrete
  release.

Both are frozen dataclasses (immutable, hashable), so they work as dict keys and set
members throughout the resolver, registry, and lockfile.

## Segment rules

Each of `vendor`, `library`, `name` must start with a letter or digit and contain
only letters, digits, `_`, `.`, or `-` (no `:`). A malformed segment raises
`InvalidVlnvError`.

## `PackageRef`

| Member | Description |
|--------|-------------|
| `PackageRef(vendor, library, name)` | Construct; validates segments. |
| `PackageRef.parse("v:l:n") -> PackageRef` | Parse a 3-part string. Raises `InvalidVlnvError`. |
| `vendor`, `library`, `name` | The segments. |
| `with_version(v) -> Vlnv` | Attach a `Version`/`OpaqueVersion` instance (or a SemVer string) to get a `Vlnv`. |
| `str(ref)` | `"vendor:library:name"`. |

## `Vlnv`

| Member | Description |
|--------|-------------|
| `Vlnv(vendor, library, name, version)` | Construct (`version` is an [`AnyVersion`](versioning.md): `Version` or `OpaqueVersion`). |
| `Vlnv.parse("v:l:n:ver", scheme="semver") -> Vlnv` | Parse a 4-part string; `scheme="opaque"` parses the version as a non-SemVer token. Raises `InvalidVlnvError`. |
| `vendor`, `library`, `name`, `version` | The fields (`version` is a `Version` or [`OpaqueVersion`](versioning.md)). |
| `ref` | The version-less `PackageRef` for this identity. |
| `str(vlnv)` | `"vendor:library:name:version"`. |

`Vlnv.parse` defaults to the `semver` scheme (a non-SemVer version raises); pass
`scheme="opaque"` for an opaque core. The CLI's `pull`/`yank`, which receive a bare
VLNV string with no scheme, try SemVer first and fall back to opaque.

## Errors

`InvalidVlnvError` (subclass of `HdlPackagerError` / `ValueError`).

## Example

```python
from hdlpkg import PackageRef, Vlnv

ref = PackageRef.parse("acme:comm:uart")
vlnv = ref.with_version("1.2.0")
assert str(vlnv) == "acme:comm:uart:1.2.0"
assert vlnv.ref == ref                 # round-trips back to the key
assert Vlnv.parse("acme:comm:uart:1.2.0") == vlnv
```
