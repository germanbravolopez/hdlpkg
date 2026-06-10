# Architecture — HDL IP Packager

> Agent quick-start: [docs/ai_agent_instructions.md](./ai_agent_instructions.md) | Find anything: [docs/INDEX.md](./INDEX.md) | Research basis: [docs/research/state_of_the_art.md](./research/state_of_the_art.md)

This document is the technical reference for how the packager is built and how it
is meant to grow. Sections marked **(implemented)** exist and are tested today;
**(planned)** sections are designed but not yet built (tracked as open issues) — see
[progress_tracker.md](./progress_tracker.md) for status.

---

## 1. The big picture

The packager is a Python library (`hdl_ip_packager`) with a thin CLI (`hdlpkg`). It
takes a tree of IP cores — each described by an `ip.toml` manifest — and provides
the **manifest → resolve → lock → fetch → generate** pipeline that lets a design
reuse versioned IP the way software reuses packages.

```
            author writes                 resolver picks              backends consume
           ┌───────────────┐   reads     ┌───────────────┐  writes   ┌───────────────┐
  ip.toml  │   Manifest    │───────────> │  Resolution   │─────────> │  ip.lock      │
 (manifest)│  (identity,   │             │ (1 Vlnv per   │           │ (exact vlnvs  │
           │   deps, fset) │             │   package)    │           │  + checksums) │
           └───────────────┘             └───────┬───────┘           └───────────────┘
                                                 │ fetch (verified)
                                                 ▼
                                      ┌────────────────────┐  generate  ┌───────────────┐
                                      │  Cache / Registry  │──────────> │ EDAM / tool   │
                                      │ (content-addressed)│            │ files, IP-XACT│
                                      └────────────────────┘            └───────────────┘
```

---

## 2. Module map

All source lives under [src/hdl_ip_packager/](../src/hdl_ip_packager/). This page is
the *design* view (how modules fit and why); for the per-module **reference** (public
API, behavior, errors, examples) see the [module manual](modules/README.md), and for a
task-oriented intro see the [user guide](user_guide.md).

| Module | File | Status | Responsibility |
|--------|------|--------|----------------|
| Versioning | [version.py](../src/hdl_ip_packager/version.py) | implemented | `Version` (SemVer) + `VersionConstraint`, `compatibility_group`, and the non-SemVer schemes `CalVer` / `MonotonicVersion` / `OpaqueVersion` (`parse_version`) |
| Identity | [vlnv.py](../src/hdl_ip_packager/vlnv.py) | implemented | `PackageRef` (`vendor:library:name`) and `Vlnv` (+`:version`) |
| Manifest | [manifest.py](../src/hdl_ip_packager/manifest.py) | implemented | Parse/validate `ip.toml` → `Manifest` (identity, deps, filesets, targets) |
| Scaffolder | [scaffold.py](../src/hdl_ip_packager/scaffold.py) | implemented | Pure renderer for a starter `ip.toml` (behind `hdlpkg init`) |
| Errors | [exceptions.py](../src/hdl_ip_packager/exceptions.py) | implemented | One exception hierarchy rooted at `HdlPackagerError` |
| CLI | [cli.py](../src/hdl_ip_packager/cli.py) | implemented | `hdlpkg` entry point; all commands implemented (`info`/`validate`/`init`/`add`/`resolve`/`install`/`pack`/`publish`/`pull`/`yank`/`login`/`logout`/`gen`/`tree`/`export-ipxact`) |
| Resolver | [resolver.py](../src/hdl_ip_packager/resolver.py) | implemented | Constraints → selected `Vlnv`(s) (backtracking, Cargo-style unification, `[resolution] on-conflict` policy, scheme-aware) |
| Lockfile | [lockfile.py](../src/hdl_ip_packager/lockfile.py) | implemented | Serialize/parse/verify `ip.lock` (a `Resolution` + per-core source + SHA-256) |
| Cache | [cache.py](../src/hdl_ip_packager/cache.py) | implemented | Content-addressed local blob store (SHA-256 key, verify-on-read, atomic writes) |
| Registry | [registry.py](../src/hdl_ip_packager/registry.py) | implemented (local + HTTP + OCI, all writable) | Abstract `Registry` + local-dir/writable-local/HTTP/OCI backends + `registry_from_location` scheme dispatch + graph walker (Git tracked as an issue) |
| Credentials | [credentials.py](../src/hdl_ip_packager/credentials.py) | implemented | Per-host bearer tokens for private registries (`hdlpkg login`); pure `CredentialStore` + TOML load/save |
| Packaging | [packaging.py](../src/hdl_ip_packager/packaging.py) | implemented | Build/read the deterministic `.ipkg` artifact (`pack_core`, `extract_ipkg`) |
| Backends | [backends/](../src/hdl_ip_packager/backends/) | implemented (Verilator, Vivado, Icarus, GHDL, Yosys) | EDAM-like intermediate (`build_eda_design`) → tool inputs behind `hdlpkg gen` |
| Name-mangling | [mangle.py](../src/hdl_ip_packager/mangle.py) | implemented (SystemVerilog + VHDL packages) | Rewrite coexisting package names so two versions build together under `gen` |
| Tree view | [treeview.py](../src/hdl_ip_packager/treeview.py) | implemented | `render_dependency_tree` → ASCII dependency graph behind `hdlpkg tree` |
| IP-XACT | [ipxact.py](../src/hdl_ip_packager/ipxact.py) | implemented | `to_ipxact` → IEEE 1685-2014 component XML behind `hdlpkg export-ipxact` |
| SBOM | [sbom.py](../src/hdl_ip_packager/sbom.py) | implemented (CycloneDX) | `build_cyclonedx` → deterministic CycloneDX 1.5 SBOM behind `hdlpkg pack --sbom` |

The dependency direction is strictly one-way and acyclic:

```
exceptions  ← version ← vlnv ← manifest ← {resolver, cli}
                          ↑        ↑
                     scaffold    registry
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
  `description`, `license`, `authors`, `top`, `keywords`, and an optional `scheme`
  (`semver` default / `calver` / `monotonic` / `opaque` — how the `version` is
  interpreted and ordered).
- `[dependencies]` — `"vendor:library:name" = "<constraint>"`.
- `[resolution]` — optional `on-conflict` policy (`fail_on_conflict` default /
  `use_latest` / `isolate_namespaces`) for an incompatible version conflict.
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
the directory scan and digesting. The recorded checksum is the **packed-content
digest** of the core (the same SHA-256 the cache keys on and the registry serves).

---

## 4. Subsystem designs

### Resolver *(implemented — [resolver.py](../src/hdl_ip_packager/resolver.py))*
Input: the root `Manifest` + `available: Mapping[PackageRef, Sequence[Manifest]]`
(the *manifests* of each package's known versions, so a candidate's own
`[dependencies]` and declared version *scheme* drive the transitive solve). Output:
a `Resolution` exposing `vlnvs` / `by_ref` / `warnings`, usually one `Vlnv` per
package and possibly more under `isolate_namespaces`.
- **Compatibility unification (Cargo-style)** — dependents in the same compatibility
  group (`compatibility_group`: same major for SemVer; for `0.y` the minor) unify to
  the newest version satisfying them all. A diamond on `^1.0` + `^1.1` collapses to
  one `1.1.x`.
- **Conflict policy** — only a genuinely *incompatible* conflict (two majors, or two
  exact pins of an `opaque` core) is governed by the `[resolution] on-conflict`
  policy (`--on-conflict` overrides it): `fail_on_conflict` (default, raise),
  `use_latest` (collapse to newest + warn), `isolate_namespaces` (keep all in the
  lock/tree; `gen` [name-mangles](#name-mangling) coexisting SystemVerilog/VHDL packages
  so they build together — module/entity coexistence is still refused).
- **Version scheme** — `[package].scheme` selects how a core's versions are parsed,
  ordered, and grouped: `semver` (default; non-SemVer rejected at parse), `calver`
  (ordered numeric `2024.1`, year-as-major), `monotonic` (an ordered revision `r3`,
  one shared group), or `opaque` (an uninterpreted token, pinned exactly). For the
  non-SemVer schemes a bare constraint means *exact*; `^`/`~`/ranges are explicit.
  Non-SemVer VLNVs round-trip through the lockfile via a `scheme` marker.
- **Newest-compatible** selection; pre-releases excluded unless a constraint's
  operand is itself a pre-release of the same core (the `VersionConstraint` rule).
- **Backtracking search** over candidate sets keyed per `(package, compatibility
  group)` node (newest-first; a candidate conflicting with an already-chosen version
  in its group is rejected and the search falls back); a post-search policy fold and
  a reachability pass prune `use_latest` orphans. Pure, so it does no I/O; the
  registry/cache layer supplies `available`. Can be lowered to a SAT/CDCL solver
  later without changing the contract.

### Cache *(implemented — [cache.py](../src/hdl_ip_packager/cache.py))*
`ContentAddressedCache` is a local blob store keyed by the SHA-256 of each blob's
own bytes (sharded git-style as `<root>/sha256/ab/cdef...`). It is **verify-on
-read**: `get()` recomputes the digest and raises `RegistryError` if it disagrees
with the requested key, so a corrupted/tampered blob fails closed. Writes are
atomic (temp file + `os.replace`) and idempotent (content-addressing dedupes).
`default_cache_root()` is a user-level dir (`~/.hdlpkg/cache`) for cross-project
offline reuse. The registry backends fetch into this store; a blob is a core's
packed `.ipkg` (see Packaging below).

### Registry *(implemented: local + HTTP + OCI — [registry.py](../src/hdl_ip_packager/registry.py))*
`Registry` is an ABC with `versions()`, `manifest()`, `artifact_bytes()`, `publish_core()`,
and a shared `fetch()` that stores a core's packed `.ipkg` in the content-addressed cache
(verified). `available_from_registry()` walks the dependency graph to build the
`Mapping[PackageRef, Sequence[Manifest]]` the resolver consumes. Four backends ship:
- **`LocalDirectoryRegistry`** — cores discovered by scanning directory trees for
  `ip.toml` (the `examples/` layout); read-only.
- **`LocalRegistry`** — a writable, append-only local directory store (publish / pull /
  yank), with a `.yanked` marker that retires a version without breaking old lockfiles.
- **`HttpRegistry`** — a network registry over a simple HTTP layout
  (`{base}/{vendor}/{library}/{name}/versions.json` + `.../{version}/{ip.toml,core.ipkg}`):
  reads via `GET`, publishes via `PUT` (any `PUT`-capable store — a small service, object
  storage, WebDAV — can host it).
- **`OciRegistry`** — a network registry over the **OCI distribution v2 API**, so cores
  live as OCI artifacts in any standard registry (Harbor, Artifactory, Nexus, GitLab, Zot,
  ECR/ACR). A core's `ip.toml` is the artifact config blob and its `.ipkg` is the single
  layer, tagged with the version; the package maps to repository
  `{prefix}/{vendor}/{library}/{name}`. `oci://` uses HTTPS, `oci+http://` plaintext.

**`registry_from_location(location, credentials=…)`** is the single entry point the CLI
uses: it dispatches a location string to the right backend by URL scheme (bare path /
`path:` → local, `http(s)://` → HTTP, `oci://` / `oci+http://` → OCI) and wires in the
stored token, so the rest of the CLI is backend-agnostic and the on-disk lockfile/protocol
surface is stable. The network backends are **private by design**: a per-host bearer token
from [credentials.py](../src/hdl_ip_packager/credentials.py) (set by `hdlpkg login`)
authenticates a self-hosted registry, so teams share IP inside a company network without
publishing publicly. A core's "artifact" is its deterministic `.ipkg` (see Packaging
below), so its SHA-256 is the same content address the cache keys on and the lockfile pins.

A **Git-backed channel** remains a tracked open issue (it needs `git` + a live remote to
build and test honestly). OCI authentication supports both a **direct bearer** (a
username-less credential, for self-hosted/static-token registries) and the **OCI
token-exchange** flow (`OciRegistry` answers a `401` + `WWW-Authenticate: Bearer
realm=...` by exchanging HTTP Basic credentials -- or going anonymous -- at the realm
for a scoped access token, then retrying), so managed Harbor/cloud registries work too.

### Credentials *(implemented — [credentials.py](../src/hdl_ip_packager/credentials.py))*
A pure `CredentialStore` maps a **registry host** (`oci://harbor.corp/ip/a` and
`.../ip/b` share one credential for `harbor.corp`) to a `Credential` (a secret plus an
optional username -> direct bearer vs. HTTP Basic for the token exchange), with TOML
serialization (reading the legacy `[tokens]` form too); the thin
`load_credentials`/`save_credentials` pair is the only I/O, writing
`~/.hdlpkg/credentials.toml` (override with `HDLPKG_CREDENTIALS`) owner-only where the OS
allows. `hdlpkg login [-u]`/`logout` manage it; `registry_from_location` reads it, with
`docker login` (`~/.docker/config.json`) credentials merged in as a fallback.

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

### Name-mangling *(implemented for SystemVerilog + VHDL packages — [mangle.py](../src/hdl_ip_packager/mangle.py))*
When `isolate_namespaces` keeps two versions of one package, they collide in HDL's one
global namespace. Under `gen` the pure `mangle.py` rewrites each version's **package**
name to a unique one (`bus_pkg` → `bus_pkg__v1_1_0`) and rewrites every consumer's
references to the version it resolved to. Each language has a comment/string-aware
scanner that touches only unambiguous package positions — SystemVerilog
(`package`/`endpackage`/`import`/`::`) and VHDL, case-insensitively
(`package`/`use work.<name>`) — so a coincidental signal name or a name in a
comment/string is never changed, no parser needed. The CLI materializes the rewritten
tree into `<output>/src/` and builds over it (`build_eda_design(allow_multiversion=True)`).
*Module*/interface (SV) and *entity* (VHDL) coexistence is refused (ambiguous
instantiation position needs a real HDL frontend).

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
returns exit code 1 with a single `error: …` line.

---

## 6. Conventions that keep this scalable

- **Pure core, I/O at the edges.** Parsing/logic modules take and return values;
  filesystem/network lives in the CLI and registry/cache layer. This is why
  the test suite is fast and deterministic.
- **One exception family.** Everything derives from `HdlPackagerError`.
- **Typed and linted.** `mypy --strict` on `src/`, `ruff` on everything.
- **Tested with the code.** New logic ships with unit tests; see
  [tests/README.md](../tests/README.md).

See [progress_tracker.md](./progress_tracker.md) for the ordered roadmap.
