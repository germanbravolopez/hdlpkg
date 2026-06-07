# Resolver — `resolver.py`

Turns a root manifest plus the set of available core versions into one concrete
version per package. Pure module (no I/O): the available versions are passed in, so
the solve is deterministic and fully unit-testable.

- **Source**: [src/hdl_ip_packager/resolver.py](../../src/hdl_ip_packager/resolver.py)
- **Import**: `from hdl_ip_packager import resolve, Resolution`

## Purpose

Given what a core depends on (constraints) and what versions exist, pick exactly one
`Vlnv` per package that satisfies *every* accumulated constraint. The result is what
the [lockfile](lockfile.md) records and what [install](cli.md)/[gen](backends.md)
build on.

## API

```python
def resolve(
    root: Manifest,
    available: Mapping[PackageRef, Sequence[Manifest]],
) -> Resolution
```

- `root` — the top-level [manifest](manifest.md) whose `[dependencies]` drive the
  solve.
- `available` — for each package, the **manifests** of the versions a registry/cache
  offers. Manifests (not bare versions) so each candidate's own `[dependencies]` can
  be followed transitively. In practice this map is built by
  [`available_from_registry`](registry.md).

**`Resolution`** is a frozen dataclass:

| Member | Description |
|--------|-------------|
| `selected` | `Mapping[PackageRef, Vlnv]` — one chosen VLNV per package |
| `vlnvs` (property) | the selected VLNVs sorted by string (deterministic order) |

## Algorithm & guarantees

- **Single version per package**, fail-on-conflict — HDL elaboration cannot host two
  versions of the same module (unlike npm's nesting).
- **Newest-compatible**: among versions satisfying every accumulated constraint, the
  highest is preferred.
- **Transitive**: a chosen candidate's own dependencies are added and solved too.
- **Diamond-aware**: when two paths require the same package, their constraints are
  intersected.
- **Backtracking**: if a newest-first choice makes some transitive constraint
  unsatisfiable, the search falls back to older versions before giving up. (Graphs
  are small today; this can be swapped for a SAT/CDCL solver later without changing
  the public contract.)
- **Pre-release-aware**: pre-releases are excluded unless a constraint targets that
  exact base version (the [version](versioning.md) rule).

## Errors

`ResolutionError` if no assignment satisfies all constraints. The message names the
offending package, the constraints on it, and the versions that were on offer.

## Example

```python
from hdl_ip_packager import Manifest, resolve
from hdl_ip_packager.registry import LocalDirectoryRegistry, available_from_registry

root = Manifest.from_path("examples/uart/ip.toml")
registry = LocalDirectoryRegistry([Path("examples")])
resolution = resolve(root, available_from_registry(registry, root))
for vlnv in resolution.vlnvs:
    print(vlnv)            # acme:common:fifo:1.0.0
```

`hdlpkg tree` prints this resolution as a graph; see [the CLI page](cli.md#tree).
