# Resolver — `resolver.py`

Turns a root manifest plus the set of available core versions into the chosen
version(s) per package. Pure module (no I/O): the available versions are passed in, so
the solve is deterministic and fully unit-testable.

- **Source**: [src/hdl_ip_packager/resolver.py](../../src/hdl_ip_packager/resolver.py)
- **Import**: `from hdl_ip_packager import resolve, Resolution`

## Purpose

Given what a core depends on (constraints) and what versions exist, pick the
version(s) of each package that satisfy every accumulated constraint. The result is
what the [lockfile](lockfile.md) records and what [install](cli.md)/[gen](backends.md)
build on.

## API

```python
def resolve(
    root: Manifest,
    available: Mapping[PackageRef, Sequence[Manifest]],
    policy: ConflictPolicy | None = None,
) -> Resolution
```

- `root` — the top-level [manifest](manifest.md) whose `[dependencies]` drive the
  solve.
- `available` — for each package, the **manifests** of the versions a registry/cache
  offers. Manifests (not bare versions) so each candidate's own `[dependencies]` and
  declared version *scheme* can be followed. In practice this map is built by
  [`available_from_registry`](registry.md).
- `policy` — how to treat an *incompatible* conflict; defaults to the root manifest's
  `[resolution] on-conflict` (`fail_on_conflict` if unset). See below.

**`Resolution`** is a frozen dataclass:

| Member | Description |
|--------|-------------|
| `packages` | `tuple[Vlnv, ...]` — every selected VLNV (usually one per package) |
| `vlnvs` (property) | the selected VLNVs sorted by string (deterministic order) |
| `by_ref` (property) | `dict[PackageRef, tuple[Vlnv, ...]]` — selections grouped by package |
| `warnings` | `tuple[str, ...]` — any policy-driven compromise (a `use_latest` collapse, an isolated coexistence) |

## Algorithm & guarantees

- **Compatibility unification (Cargo-style)**: dependents whose ranges fall in the
  same compatibility group — same major for SemVer (see
  [`compatibility_group`](versioning.md)) — always unify to the newest version
  satisfying them all. A diamond on `^1.0` + `^1.1` collapses to one `1.1.x`.
- **Conflict policy**: only a genuinely *incompatible* conflict (two SemVer majors, or
  two distinct exact pins of an `opaque`-scheme package) is governed by the
  [`ConflictPolicy`](manifest.md):
  - `fail_on_conflict` (default) — raise `ResolutionError`.
  - `use_latest` — collapse to the newest of the conflicting versions (single copy),
    prune orphans, and record a `warning`.
  - `isolate_namespaces` — keep every incompatible version in the resolve/lock/tree
    (multi-version bookkeeping). `gen` then [name-mangles](mangle.md) coexisting
    SystemVerilog/VHDL packages so they build together (module/entity coexistence is refused).
- **Scheme-aware**: a package's `[package].scheme` chooses how its versions group —
  `semver` (by major), `calver` (by year), `monotonic` (one shared group), or
  `opaque` (each exact pin its own group; dependents must pin exactly). See
  [versioning](versioning.md).
- **Newest-compatible**, **transitive**, **backtracking** (a newest-first choice that
  makes a transitive constraint unsatisfiable falls back to older versions), and
  **pre-release-aware** (the [version](versioning.md) rule). The search is keyed per
  *(package, compatibility group)* node, so two incompatible majors are independent
  nodes that each resolve to one version. Can be swapped for a SAT/CDCL solver later
  without changing the public contract.

## Errors

`ResolutionError` if no assignment satisfies all constraints, or an incompatible
conflict is hit under `fail_on_conflict`. The message names the offending package, its
constraints, and the versions on offer (or the conflicting versions).

## Example

```python
from hdl_ip_packager import Manifest, resolve
from hdl_ip_packager.registry import LocalDirectoryRegistry, available_from_registry

root = Manifest.from_path("examples/uart/ip.toml")
registry = LocalDirectoryRegistry([Path("examples")])
resolution = resolve(root, available_from_registry(registry, root))
for vlnv in resolution.vlnvs:
    print(vlnv)            # acme:common:fifo:1.0.0
for warning in resolution.warnings:
    print("warning:", warning)
```

`hdlpkg tree` prints this resolution as a graph; see [the CLI page](cli.md#tree).
