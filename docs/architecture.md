# Architecture — HDL IP Packager

> Agent quick-start: [docs/ai_agent_instructions.md](./ai_agent_instructions.md) | Find anything: [docs/INDEX.md](./INDEX.md) | Research basis: [docs/research/state_of_the_art.md](./research/state_of_the_art.md)

This document is the technical reference for how the packager is built and how it
is meant to grow. Sections marked **(implemented)** exist and are tested today;
**(planned)** sections are designed but stubbed — see
[progress_tracker.md](./progress_tracker.md) for status.

---

## 1. The big picture

The packager is a Python library (`hdl_ip_packager`) with a thin CLI (`hdlpkg`). It
takes a tree of IP cores — each described by an `ip.toml` manifest — and provides
the **manifest → resolve → lock → fetch → generate** pipeline that lets a design
reuse versioned IP the way software reuses packages.

```
            author writes                resolver picks            backends consume
          ┌───────────────┐   reads    ┌───────────────┐  writes  ┌───────────────┐
  ip.toml │   Manifest    │──────────▶ │   Resolution  │────────▶ │  ip.lock      │
 (manifest)│  (identity,  │            │ (1 Vlnv per   │          │ (exact vlnvs  │
          │   deps, fset) │            │   package)    │          │  + checksums) │
          └───────────────┘            └───────┬───────┘          └───────────────┘
                                               │ fetch (verified)
                                               ▼
                                     ┌───────────────────┐  generate  ┌──────────────┐
                                     │  Cache / Registry │──────────▶ │ EDAM / tool  │
                                     │ (content-addressed)│           │ files, IP-XACT│
                                     └───────────────────┘            └──────────────┘
```

---

## 2. Module map

All source lives under [src/hdl_ip_packager/](../src/hdl_ip_packager/).

| Module | File | Status | Responsibility |
|--------|------|--------|----------------|
| Versioning | [version.py](../src/hdl_ip_packager/version.py) | implemented | SemVer 2.0.0 `Version` + `VersionConstraint` (parse, precedence, matching) |
| Identity | [vlnv.py](../src/hdl_ip_packager/vlnv.py) | implemented | `PackageRef` (`vendor:library:name`) and `Vlnv` (+`:version`) |
| Manifest | [manifest.py](../src/hdl_ip_packager/manifest.py) | implemented | Parse/validate `ip.toml` → `Manifest` (identity, deps, filesets, targets) |
| Scaffolder | [scaffold.py](../src/hdl_ip_packager/scaffold.py) | implemented | Pure renderer for a starter `ip.toml` (behind `hdlpkg init`) |
| Errors | [exceptions.py](../src/hdl_ip_packager/exceptions.py) | implemented | One exception hierarchy rooted at `HdlPackagerError` |
| CLI | [cli.py](../src/hdl_ip_packager/cli.py) | implemented | `hdlpkg` entry point; `info`/`validate`/`init` work, rest are wired stubs |
| Resolver | [resolver.py](../src/hdl_ip_packager/resolver.py) | implemented | Constraints → one concrete `Vlnv` per package (backtracking, newest-compatible) |
| Lockfile | [lockfile.py](../src/hdl_ip_packager/lockfile.py) | implemented | Serialize/parse/verify `ip.lock` (a `Resolution` + per-core source + SHA-256) |
| Cache | [cache.py](../src/hdl_ip_packager/cache.py) | implemented | Content-addressed local blob store (SHA-256 key, verify-on-read, atomic writes) |
| Registry | [registry.py](../src/hdl_ip_packager/registry.py) | planned | Abstract `Registry`; local/Git/HTTP/OCI backends that fetch into the cache |

The dependency direction is strictly one-way and acyclic:

```
exceptions  ← version ← vlnv ← manifest ← {resolver, cli}
                          ↑        ↑
                       scaffold    registry (planned)
```

`scaffold` is pure too (it renders a manifest string from `version`/`vlnv` and is
consumed by `cli`). `version`, `vlnv`, and `manifest` are **pure** (no I/O, no globals). That purity
is deliberate: it is what makes them exhaustively unit-testable and is the model
every new module should follow (see [ai_agent_instructions.md](./ai_agent_instructions.md)).

---

## 3. Data model

### Identity — VLNV
A core is named `vendor:library:name:version`, e.g. `acme:comm:uart:1.2.0` — the
IP-XACT/FuseSoC convention. `PackageRef` is the version-less triple used as a
*dependency key*; `Vlnv` is a fully-qualified release. Segments must start with a
letter/digit and contain only `[A-Za-z0-9_.-]`.

### Versions and constraints
`Version` implements full SemVer 2.0.0 precedence (pre-release ordering per §11,
build metadata ignored). `VersionConstraint` parses an *AND* of comparators:

| Form | Meaning |
|------|---------|
| `^1.2.3` (and bare `1.2.3`) | `>=1.2.3, <2.0.0` (caret; `0.x` narrows) |
| `~1.2.3` | `>=1.2.3, <1.3.0` |
| `>=`, `>`, `<=`, `<`, `=`/`==` | the obvious comparisons |
| `>=1.0.0,<2.0.0` | comma = AND |
| `*` / `any` / empty | any stable version |

**Pre-release rule:** a constraint built from stable operands never matches a
pre-release; a pre-release only matches when some comparator's operand is itself a
pre-release of the same `MAJOR.MINOR.PATCH` (the Cargo rule).

### Manifest — `ip.toml`
The per-core, author-written manifest. Schema (full example in
[manifest.py](../src/hdl_ip_packager/manifest.py) and the [README](../README.md)):

- `[package]` — `vendor`, `library`, `name`, `version` (required); plus
  `description`, `license`, `authors`, `top`, `keywords`.
- `[dependencies]` — `"vendor:library:name" = "<constraint>"`.
- `[filesets.<id>]` — `files` (list), `type` (HDL kind), optional `depend`
  (targets that pull it in).
- `[targets.<id>]` — `toolflow`, `filesets` (must reference defined filesets),
  optional `top`.

Validation is strict and every error names the offending field via `ManifestError`.

### Lockfile — `ip.lock` *(implemented — [lockfile.py](../src/hdl_ip_packager/lockfile.py))*
Generated record of a resolve: the exact `Vlnv` chosen for every package plus a
SHA-256 integrity `checksum` and a `source`. Committed to version control for
reproducible, verifiable builds (the Cargo/Orbit/Go model). Serialized as TOML
with a schema `version` and a `[[package]]` array sorted by VLNV (stable, diff
-friendly); `Lockfile.from_toml` round-trips it and `verify()` fails closed on a
missing/mismatched checksum. The module is pure — the CLI's `resolve` command does
the directory scan and digesting. The recorded checksum currently covers the
manifest bytes; M3 widens it to the full packaged content without changing the
file format.

---

## 4. Subsystems to be built (design intent)

### Resolver *(implemented — [resolver.py](../src/hdl_ip_packager/resolver.py))*
Input: the root `Manifest` + `available: Mapping[PackageRef, Sequence[Manifest]]`
(the *manifests* of each package's known versions, so a candidate's own
`[dependencies]` drive the transitive solve). Output: a `Resolution` = one `Vlnv`
per package satisfying every constraint.
- **Single version per package**, fail-on-conflict — HDL elaboration cannot host
  two versions of the same module (unlike npm's nesting).
- **Newest-compatible** selection; pre-releases excluded unless a constraint's
  operand is itself a pre-release of the same core (the `VersionConstraint` rule).
- **Backtracking search** over candidate sets (newest-first, constraints
  accumulate as dependents are chosen; a candidate that conflicts with an
  already-chosen version is rejected and the search falls back to older versions).
  Pure, so it does no I/O; the registry/cache layer supplies `available`. Can be
  lowered to a SAT/CDCL solver later without changing the contract (version
  selection is NP-complete in general).

### Cache *(implemented — [cache.py](../src/hdl_ip_packager/cache.py))*
`ContentAddressedCache` is a local blob store keyed by the SHA-256 of each blob's
own bytes (sharded git-style as `<root>/sha256/ab/cdef...`). It is **verify-on
-read**: `get()` recomputes the digest and raises `RegistryError` if it disagrees
with the requested key, so a corrupted/tampered blob fails closed. Writes are
atomic (temp file + `os.replace`) and idempotent (content-addressing dedupes).
`default_cache_root()` is a user-level dir (`~/.hdlpkg/cache`) for cross-project
offline reuse. The registry backends (M4) fetch into this store; what a blob
contains is defined by packaging (M5).

### Registry *(planned — [registry.py](../src/hdl_ip_packager/registry.py))*
`Registry` is an ABC with `versions()`, `fetch()`, `publish()` so multiple
backends coexist: a local directory, a Git-backed channel, an HTTP index, and —
the differentiator — an **OCI artifact** registry (reuse Docker-registry infra:
content-addressable, immutable, ubiquitous). `fetch()` populates the
content-addressed cache above. Publishing is append-only with **yank** (retire
without breaking old lockfiles).

### Packaging & backends *(planned)*
- `pack` → a distributable `.ipkg` artifact (sources + manifest + integrity).
- `gen` → an EDAM-like intermediate that feeds simulators/synthesis (FuseSoC's
  tool-flow abstraction), keeping tool specifics out of the core.
- `export-ipxact` → IEEE 1685 XML for Vivado/other-tool interop.

### Supply-chain *(planned)*
Checksums first; then optional Sigstore (cosign) signing and an SBOM emitted at
`pack` time, matching the 2026 SLSA/SBOM baseline.

---

## 5. Data flow today (implemented path)

`hdlpkg info ip.toml`:

```
cli.main(["info", path])
  → Manifest.from_path(path)
      → tomllib.loads(text)
      → _parse_identity → PackageRef + Version.parse → Vlnv
      → _parse_dependencies → PackageRef.parse + VersionConstraint.parse
      → _parse_filesets / _parse_targets (cross-validate target→fileset refs)
  → print identity, dependencies, filesets, targets
```

Every step raises a subclass of `HdlPackagerError`; `cli.main` catches it and
returns exit code 1 with a single `error: …` line. Planned commands return exit
code 2 with a "not implemented" notice rather than pretending to work.

---

## 6. Conventions that keep this scalable

- **Pure core, I/O at the edges.** Parsing/logic modules take and return values;
  filesystem/network lives in the CLI and (future) registry layer. This is why
  the test suite is fast and deterministic.
- **One exception family.** Everything derives from `HdlPackagerError`.
- **Typed and linted.** `mypy --strict` on `src/`, `ruff` on everything.
- **Tested with the code.** New logic ships with unit tests; see
  [tests/README.md](../tests/README.md).

See [progress_tracker.md](./progress_tracker.md) for the ordered roadmap.
