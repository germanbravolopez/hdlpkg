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

All source lives under [src/hdl_ip_packager/](../src/hdl_ip_packager/). This page is
the *design* view (how modules fit and why); for the per-module **reference** (public
API, behavior, errors, examples) see the [module manual](modules/README.md), and for a
task-oriented intro see the [user guide](user_guide.md).

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
| Registry | [registry.py](../src/hdl_ip_packager/registry.py) | implemented (local + HTTP) | Abstract `Registry` + local-dir/HTTP/writable-local backends + graph walker (Git/OCI tracked as issues) |
| Packaging | [packaging.py](../src/hdl_ip_packager/packaging.py) | implemented | Build/read the deterministic `.ipkg` artifact (`pack_core`, `extract_ipkg`) |
| Backends | [backends/](../src/hdl_ip_packager/backends/) | implemented (Verilator, Vivado, Icarus, GHDL, Yosys) | EDAM-like intermediate (`build_eda_design`) → tool inputs behind `hdlpkg gen` |
| Tree view | [treeview.py](../src/hdl_ip_packager/treeview.py) | implemented | `render_dependency_tree` → ASCII dependency graph behind `hdlpkg tree` |
| IP-XACT | [ipxact.py](../src/hdl_ip_packager/ipxact.py) | implemented | `to_ipxact` → IEEE 1685-2014 component XML behind `hdlpkg export-ipxact` |
| SBOM | [sbom.py](../src/hdl_ip_packager/sbom.py) | implemented (CycloneDX) | `build_cyclonedx` → deterministic CycloneDX 1.5 SBOM behind `hdlpkg pack --sbom` |

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

### Registry *(implemented: local + HTTP — [registry.py](../src/hdl_ip_packager/registry.py))*
`Registry` is an ABC with `versions()`, `manifest()`, `artifact_bytes()`, and a
shared `fetch()` that stores a core's artifact in the content-addressed cache
(verified). `available_from_registry()` walks the dependency graph to build the
`Mapping[PackageRef, Sequence[Manifest]]` the resolver consumes. Two backends ship:
- **`LocalDirectoryRegistry`** — cores discovered by scanning directory trees for
  `ip.toml` (the `examples/` layout); backs `hdlpkg resolve`/`install`.
- **`HttpRegistry`** — cores served by a static HTTP index
  (`{base}/{vendor}/{library}/{name}/versions.json` + `.../{version}/ip.toml`).

Still designed but **tracked as open issues** (they need external tooling / live
services to build and test): a **Git-backed channel** and — the differentiator —
an **OCI artifact** registry (reuse Docker-registry infra: content-addressable,
immutable, ubiquitous). Publishing (append-only with **yank**) lands with M5.
A core's "artifact" is its manifest bytes until packaging (M5) defines the packed
form; the interface does not change when it does.

### Packaging *(implemented — [packaging.py](../src/hdl_ip_packager/packaging.py))*
`pack_core` builds a **deterministic** `.ipkg` (a gzip+tar of `ip.toml` plus every
fileset file, with sorted entries, fixed mode/owner, zero mtime and gzip header),
so a core always packs to byte-identical bytes and its SHA-256 is a stable content
address. `extract_ipkg` unpacks it with path-traversal protection. The `.ipkg` is
now the unit the registry serves, the cache stores, and the lockfile pins (the
checksum is the packed-content digest). The CLI exposes `pack`, `publish`
(append-only into a writable `LocalRegistry`, with `yank` to retire a version
without breaking old lockfiles), and `pull` (fetch by VLNV into the cache, extract).

### Backends *(tool-flow generation implemented — [backends/](../src/hdl_ip_packager/backends/))*
`gen` builds a tool-agnostic EDAM-like intermediate
([edam.py](../src/hdl_ip_packager/backends/edam.py): `build_eda_design`) from the
root core, its resolved dependencies, and a chosen target, then hands it to the
`Backend` selected by the target's `toolflow`. The root contributes its target's
filesets (testbench included for `sim`, excluded for `synth`); each dependency
contributes only its synthesizable surface (its `rtl` fileset, or all non-testbench
filesets), emitted dependencies-first via a topological sort. Any selected fileset
also pulls in its declared `depend` filesets (transitively, before it), so a core
can state exactly what a fileset needs. Five backends ship: `VerilatorBackend`
(`.vc`), `VivadoBackend` (`.tcl`), `IcarusBackend` (`.cmd` + `run_iverilog.sh`),
`GhdlBackend` (`run_ghdl.sh`, VHDL-only), and `YosysBackend` (`.ys`); all are pure
(`generate` returns `{filename: text}`), so the CLI does the file writing. Tool
specifics stay out of the manifest/resolver/packaging layers.
### IP-XACT export *(implemented — [ipxact.py](../src/hdl_ip_packager/ipxact.py))*
`export-ipxact` renders a manifest as an IEEE **1685-2014** component XML via the
pure `to_ipxact`: VLNV identity, a `model` of one view + componentInstantiation per
target, and the `fileSets`. The manifest's fileset `type` values are already the
IP-XACT `fileType` vocabulary, so they map straight through. Output is well-formed
and deterministic (stdlib `ElementTree`); XSD validation is a tracked follow-up.

### Supply-chain *(SBOM implemented — [sbom.py](../src/hdl_ip_packager/sbom.py); signing planned)*
Checksums first (the packed-content SHA-256 already pins every artifact across the
cache, lockfile, and registry); then a deterministic **CycloneDX 1.5** SBOM emitted
at `pack` time via `pack --sbom` (`build_cyclonedx`: the core + its resolved
dependency components + the dependency graph). **Sigstore (cosign) keyless signing**
of the artifact + SBOM remains planned — it needs OIDC/Fulcio/Rekor infrastructure —
and is tracked as an open issue. This matches the 2026 SLSA/SBOM baseline.

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
