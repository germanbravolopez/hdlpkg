# Identity (VLNV) — `vlnv.py`

How an IP core is named. Pure module (parsing/formatting only).

- **Source**: [src/hdl_ip_packager/vlnv.py](../../src/hdl_ip_packager/vlnv.py)
- **Import**: `from hdl_ip_packager import PackageRef, Vlnv`

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
| `with_version(v) -> Vlnv` | Attach a `Version` (or version string) to get a `Vlnv`. |
| `str(ref)` | `"vendor:library:name"`. |

## `Vlnv`

| Member | Description |
|--------|-------------|
| `Vlnv(vendor, library, name, version)` | Construct (`version` is a `Version`). |
| `Vlnv.parse("v:l:n:ver") -> Vlnv` | Parse a 4-part string. Raises `InvalidVlnvError`. |
| `vendor`, `library`, `name`, `version` | The fields (`version` is a [`Version`](versioning.md)). |
| `ref` | The version-less `PackageRef` for this identity. |
| `str(vlnv)` | `"vendor:library:name:version"`. |

## Errors

`InvalidVlnvError` (subclass of `HdlPackagerError` / `ValueError`).

## Example

```python
from hdl_ip_packager import PackageRef, Vlnv

ref = PackageRef.parse("acme:comm:uart")
vlnv = ref.with_version("1.2.0")
assert str(vlnv) == "acme:comm:uart:1.2.0"
assert vlnv.ref == ref                 # round-trips back to the key
assert Vlnv.parse("acme:comm:uart:1.2.0") == vlnv
```
