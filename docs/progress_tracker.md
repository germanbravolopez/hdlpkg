# Progress Tracker — HDL IP Packager

**Rule**: Track only what is actionable now. Sections:
- **Roadmap** — the ordered plan for the project, newest milestones first to build.
- **Blocking Issues** — must-fix before the next release.
- **Open Non-Blocking Issues** — known backlog worth doing, not gating a release.
- **Backlog (deferred)** — consciously parked; revisit only if the trade-off changes.
- **Completed Milestones** — finished work, newest at the top (changelog source).
- **Archive** — entries older than ~6 months and no longer actionable.

Add new entries at the **top** of the relevant section. Do not keep an "In
Progress" list — work in progress lives on the branch. Never delete entries; move
them to Archive. Convert relative dates to absolute (e.g. "June 2026").

---

## Current Status — June 2026

**Active branch**: `main`

**Version**: `0.8.0` — the pre-1.0 completeness pass + backlog batch on top of the
M8 SBOM work: reproducible lockfile-driven builds (`install --locked`/`gen
--locked`), `hdlpkg add`, the `ip.toml` `schema` key, pack/top hardening, the `tree`
Windows fix, `resolve`/`install`/`tree --registry`, `Fileset.depend`, three more
backends (Icarus/GHDL/Yosys), and Dependabot. Shipped as `0.8.0`, not `1.0.0`: the
formats are still moving (multi-version lockfile shape and a possible `scheme` key are
recorded as open issues) and the 1.0.0 stability gate (rc soak, OCI protocol,
third-party consume) is not yet met. See the Release plan.

**Stage**: Feature-complete for the roadmap (M1–M8) plus the pre-1.0 completeness
pass; fully typed, linted, and unit-tested (268 passing tests, ~96% coverage):
- **Versioning** — SemVer 2.0.0 `Version` + `VersionConstraint` (caret/tilde/range
  grammar, pre-release precedence).
- **Identity** — `PackageRef` and `Vlnv` (`vendor:library:name:version`).
- **Manifest** — `ip.toml` parsing/validation (`[package]`, `[dependencies]`,
  `[filesets]`, `[targets]`), with an optional `schema` version for a migration path.
- **Resolver** — backtracking, newest-compatible dependency resolution (one `Vlnv`
  per package, fail-on-conflict); pure, fed by an in-memory version index.
- **Lockfile** — deterministic `ip.lock` (serialize/parse/verify a `Resolution`
  with per-core source + SHA-256), written by `hdlpkg resolve`.
- **Cache** — content-addressed local blob store (SHA-256 key, verify-on-read,
  atomic writes), populated by `hdlpkg install`.
- **Registry** — `Registry` interface + `LocalDirectoryRegistry`, `HttpRegistry`,
  and writable `LocalRegistry` (append-only + yank) backends + a dependency-graph
  walker feeding the resolver (Git/OCI backends are open Non-Blocking issues).
- **Packaging** — deterministic `.ipkg` artifact (`pack_core`/`extract_ipkg`); the
  packed-content digest is what the cache and lockfile pin.
- **Backends** — tool-flow generation (`backends/`): a pure EDAM-like intermediate
  (`build_eda_design`, honoring `Fileset.depend`) feeding Verilator, Vivado, Icarus,
  GHDL, and Yosys backends behind shared, hardened guards.
- **IP-XACT** — IEEE 1685-2014 component export (`ipxact.py`: `to_ipxact`) behind
  `hdlpkg export-ipxact`.
- **Supply-chain** — content checksums (SHA-256) everywhere, plus a deterministic
  CycloneDX SBOM (`sbom.py`: `build_cyclonedx`) emitted by `hdlpkg pack --sbom`
  (Sigstore signing deferred).
- **CLI** — all commands implemented: `info`/`validate`/`init`/`add`/`resolve`/
  `install`/`pack`/`publish`/`pull`/`yank`/`gen`/`tree`/`export-ipxact`. `install
  --locked` and `gen --locked` give reproducible, lockfile-driven builds.
- **Tooling** — pytest (markers + coverage gate + foldable summary), ruff, mypy
  strict on `src/`, CI workflow, and a cross-platform test-summary renderer.

**Next**: all roadmap milestones (M1–M8) are delivered; the remaining work toward
`1.0.0` is the stability gate (see the Release plan) — frozen formats, an `rc` soak,
the OCI protocol, and a third-party publish/consume — plus the open
backends/signing and the newly recorded versioning issues (multi-version
coexistence, unification semantics, non-SemVer schemes).

---

## Roadmap (ordered — build top-down)

> Each milestone should land with tests and a docs update. The design for every
> item is in [architecture.md](./architecture.md); the rationale is in
> [research/state_of_the_art.md](./research/state_of_the_art.md).

_All roadmap milestones (M1–M8) are delivered._ The remaining path to `1.0.0` is the
stability gate in the Release plan (frozen formats, stable CLI/registry protocol, a
third-party publish/consume, an `rc` soak) — not new features. Sigstore (cosign)
signing, the unbuilt half of M8, is tracked under Open Non-Blocking Issues (it needs
OIDC/Fulcio/Rekor infrastructure to build and test honestly).

---

## Release plan

The packager is pre-1.0, so it uses `0.MINOR.PATCH`:
- **MINOR** (`0.1 -> 0.2`) = a capability milestone; pre-1.0 it may also carry
  breaking `ip.toml` / `ip.lock` / CLI changes (the 0.x licence to iterate).
- **PATCH** (`0.2.0 -> 0.2.1`) = bug / doc fixes; no new capability, no format break.
- **`X.Y.Z-rc.N`** pre-release tags for anything risky (precedence is handled by
  `version.py`; `release.yml` already accepts these tags).

The compatibility contract SemVer tracks here is the **on-disk formats users commit
to their repos** (`ip.toml`, `ip.lock`) plus the `hdlpkg` CLI surface — more than
the Python API. Cut a release at each point a user can do something new end to end;
milestones that are not independently useful are grouped into one release.

| Version | After | User-facing capability it unlocks |
|---------|-------|-----------------------------------|
| **0.1.0** | Foundation (done) | Author + validate: `init` / `info` / `validate`; publishes the v0 `ip.toml` schema. First tagged release / release-pipeline shakedown. |
| **0.2.0** | M1 + M2 | Resolve a dependency graph to a deterministic `ip.lock` (the core value prop). |
| **0.3.0** | M3 + M4 | Fetch cores: content-addressed cache + local/Git/HTTP/OCI registries. |
| **0.4.0** | M5 | `pack` / `publish` / `pull` — the full producer/consumer loop. |
| **0.5.0** | M6 | Tool-flow generation (EDAM -> Verilator/Vivado). |
| **0.6.0** | M7 | IP-XACT (IEEE 1685) export for tool interop. |
| **1.0.0** | M8 + soak | Supply-chain (signing + SBOM) **and** the stability commitment below. |

Patch releases ship between these as fixes land. Each milestone above ends with its
release tag when it completes (see "Releasing" in the [README](../README.md)).

**1.0.0 is a promise, not "all features done."** Gate it on:
- `ip.toml` and `ip.lock` formats frozen, or a migration path exists;
- the CLI command/flag surface stable;
- the registry/OCI protocol stable;
- at least one core published and consumed by a third party;
- a `1.0.0-rc.1` soak with no format changes.

If the formats are still moving when M8 lands, release it as `0.7.0`, not `1.0.0`.

---

## Blocking Issues (must fix before the next release)

_None._

---

## Open Non-Blocking Issues

| Issue | File | Notes |
|-------|------|-------|
| Git-backed registry | `registry.py` | A `Registry` backend resolving cores from a Git channel (tags/refs). Deferred from M4: needs the `git` CLI + a remote to implement and test honestly. Mirror the `LocalDirectoryRegistry`/`HttpRegistry` shape. |
| OCI artifact registry | `registry.py` | The differentiator backend: store/fetch cores as OCI artifacts (Docker-registry infra). Deferred from M4: needs a live OCI registry (or a mock) and the manifest/blob API; significant standalone work. |
| Sigstore (cosign) artifact signing | `packaging.py`, `.github/workflows/` | The unbuilt half of M8: keyless signing of the `.ipkg` + SBOM and a verify path. Needs OIDC + Fulcio/Rekor (or a managed key) and a live transparency log to implement and test honestly — deferred like the Git/OCI backends. Checksums + SBOM already ship; this adds authenticity on top. |
| Resolve/install over HTTP/OCI + `gen` from a registry | `cli.py`, `registry.py` | `resolve`/`install`/`tree --registry DIR` now consume a **local published** `LocalRegistry` directly (the producer->consumer loop closes for local registries). Remaining: wire `HttpRegistry` into `--registry` (resolve/install over HTTP), the OCI backend, and a fetch-then-extract so `gen` can build straight from a registry (it still needs loose sources via `--search`/`pull`). |
| Validate IP-XACT against the official XSD | `ipxact.py`, tests | M7 emits well-formed, structurally-conventional 1685-2014 XML but does not validate against the Accellera XSD. Add an (optional, dev-only) schema-validation test (e.g. `xmlschema`) so structural drift is caught; consider IP-XACT 2022 and richer mapping (bus interfaces, parameters). |
| Multi-version coexistence (two versions of one package in one design) | `resolver.py`, `lockfile.py`, `backends/edam.py`, `cli.py` | **Required future feature.** Today the resolver is **single-version-per-package**, fail-on-conflict. Some designs genuinely need *incompatible majors* of one IP to coexist — e.g. the external consumer demo's `soc_conflict/`: `fifo -> bus_pkg ^1` and `legacy -> bus_pkg ^2`, where v2 is a breaking change (it renamed `DATA_WIDTH` -> `BUS_DATA_BITS`), so no single version satisfies both. The work splits into two halves with very different risk: **(a) Bookkeeping (pure, safe):** the resolver/lockfile/`tree` keep *multiple* selected versions when ranges fall in SemVer-incompatible groups; `ip.lock` records more than one version of the same package. **(b) Physical coexistence at `gen` (the hard part):** SystemVerilog/Verilog put every `module`/`package` name in **one global namespace**, so two `package bus_pkg;` declarations collide at elaboration and the tool cannot know which one a consumer's `import bus_pkg::*` means. Making them build together requires **automatic name-mangling** — rename each version's declared symbols with a version-unique suffix (`bus_pkg` -> `bus_pkg__v1` / `bus_pkg__v2`) and rewrite *every reference* in each consumer to the version *that consumer resolved to*. That means editing HDL **source**, which the tool currently treats as opaque blobs; naive regex is unsafe (comments, macros, partial-name matches, hierarchical refs), so it likely needs an HDL-aware frontend (cf. the parked "source-unit tokenizing" backlog item). VHDL is slightly better placed (logical libraries give a namespace) but still needs `library`/`use`-clause rewriting. **Until (b) is built, `gen` must refuse to emit two versions of one package** with a clear message pointing at this limitation. Cargo/npm get multi-version "for free" only because their *compiler* namespaces each package automatically; HDL gives no such thing, so we must synthesize it. |
| Unification semantics for resolution (sub-issue of multi-version) | `resolver.py` | A prerequisite decision for multi-version coexistence: **when does the resolver collapse to one version vs. keep several?** Two models: **Cargo-style (recommended)** — unify all dependents whose ranges are SemVer-compatible (same major) to the newest that satisfies them, and only allow *distinct* versions across *incompatible* majors (so the demo's `soc/` still resolves to a single `bus_pkg 1.1.0`; only `soc_conflict/` would get two). **Honor-exact-pins** — keep a distinct version per dependent whenever their selected versions differ at all, even within one major (more copies, more mangling, diverges from npm/Cargo norms). This choice changes the resolver contract and the lockfile shape, so it must be settled before (a) above lands. |
| Non-SemVer / custom version schemes | `version.py`, `manifest.py`, `resolver.py` | The tool assumes **SemVer 2.0.0** everywhere (`Version` + `VersionConstraint` parse, precedence, caret/tilde ranges). Real HDL IP is frequently versioned otherwise: date/calendar-based (`2024.1` Vivado-style, `YY.MM` CalVer), monotonic revisions (`r3`, `rev12`), `git describe` (`1.2-14-gabcdef`), or opaque vendor tags. The tool must define what happens when a manifest's `version` is **not** SemVer. Behaviors to specify: **(1)** the strict default — reject a non-SemVer `version` at manifest-parse time with a clear `ManifestError` naming the offending string (better than mis-ordering it); **(2)** an opt-in `scheme` field in `[package]` (e.g. `scheme = "semver" \| "calver" \| "opaque"`) selecting the precedence/constraint engine, giving a forward-compatible migration path; **(3)** an **opaque/pinned** mode that supports only **exact-match** constraints (no ranges, no newest-compatible selection) so such cores can still be resolved and locked **deterministically** even without a total order. Implement at least (1) explicitly before the 1.0 format freeze; (2)/(3) can follow behind the `schema`/`scheme` keys. |

---

## Backlog (deferred — low value / not currently planned)

| Issue | Why parked |
|-------|------------|
| Switch build backend setuptools→`uv`/`hatch` workflow tooling | `hatchling` backend already works and is PEP-compliant; revisit only if the team standardizes on `uv` end to end. |
| Source-unit tokenizing (auto-discover HDL deps like Orbit) | Powerful but large; only worth it after the manifest-driven flow (M1–M5) is solid. |
| Mutation testing (`mutmut`) | Validates test quality, but slow and only worth it once the implemented surface is larger. |

---

## Completed Milestones

### Release 0.8.0 — June 2026
- [x] **Tagged `0.8.0`** per the Release plan: ships the pre-1.0 completeness pass +
  the non-blocking/backlog batch that landed on `main` after the `0.7.0` tag —
  reproducible lockfile-driven builds (`install --locked`/`gen --locked`), `hdlpkg
  add`, the optional `ip.toml` `schema` key, pack-path + tool-flow `top` hardening,
  the `hdlpkg tree` Windows (cp1252) fix, `resolve`/`install`/`tree --registry`
  consuming a published `LocalRegistry`, `Fileset.depend`-aware EDAM assembly, three
  more tool-flow backends (Icarus/GHDL/Yosys), Dependabot, and the per-module user
  manual. Shipped as `0.8.0` rather than `1.0.0`: the `ip.toml`/`ip.lock` formats are
  still moving (multi-version coexistence, unification semantics, and non-SemVer
  version schemes are now recorded as Open Non-Blocking Issues) and the 1.0.0
  stability gate (an `rc` soak, the OCI registry protocol, a third-party
  publish/consume) is not yet met. Bumped `pyproject.toml` + `__init__.py`. Also
  recorded the three versioning issues above.

### Pre-1.0 completeness pass — June 2026
- [x] **Reproducible, lockfile-driven builds** (`install --locked`, `gen --locked`).
  Both build *exactly* from a committed `ip.lock` without re-resolving (the `npm ci`
  / `cargo --locked` model), verifying fetched digests against the lock and failing
  if it is missing; `hdlpkg resolve` remains the one command that updates the lock.
  Closes the "the lockfile isn't actually consumed" gap. Files: `cli.py`,
  `tests/integration/test_locked_cli.py`.
- [x] **`hdlpkg add`** inserts/updates a dependency in `ip.toml` via a pure,
  text-preserving line editor (`editing.py`) — keeps formatting/comments, refuses a
  self-dependency, and re-validates before writing. The last planned CLI stub is
  gone (the empty planned-command machinery was removed). Files: `editing.py`,
  `cli.py`, `tests/unit/test_editing.py`, `tests/unit/test_cli.py`.
- [x] **`ip.toml` schema version** — an optional top-level `schema` key (default 1);
  a manifest written for a newer schema is rejected with a clear message rather than
  mis-parsed, giving the format a migration path before the 1.0 freeze. Files:
  `manifest.py`, `tests/unit/test_manifest.py`.
- [x] **Hardening** — `pack` now rejects fileset paths that escape the core directory
  (`..`/absolute); the tool-flow `top` is validated as a safe HDL identifier before
  it is interpolated into generated scripts; and the per-backend "missing top" /
  "unsupported file type" guards were factored onto the `Backend` ABC (resolving the
  two PR-review findings). Files: `packaging.py`, `backends/base.py`, `backends/*.py`,
  `tests/integration/test_packaging.py`, `tests/unit/test_backends.py`.
- [x] **`hdlpkg tree` Windows fix** — switched the dependency-tree connectors from
  Unicode box-drawing characters to ASCII; the Unicode form raised `UnicodeEncodeError`
  on a default cp1252 Windows console. Surfaced by an external consumer demo project
  (a diamond-dependency SoC built against the tool in a venv). Added an ASCII-output
  regression test. Files: `treeview.py`, `tests/unit/test_treeview.py`.
- [x] **Resolve/install/tree from a published registry** (`--registry DIR`). These
  commands previously only scanned local source trees (`--search`); they can now
  resolve and fetch **directly from a `LocalRegistry`** that `hdlpkg publish` wrote,
  closing the producer->consumer loop for local registries (the gap the demo
  surfaced). Added `Registry.source_for` (the lockfile records `registry:<dir>`).
  HTTP/OCI registries and `gen`-from-registry remain open. Files: `cli.py`,
  `registry.py`, `tests/integration/test_registry_resolve_cli.py`.

### Non-blocking + backlog batch (develop) — June 2026
- [x] **Richer dependency fileset selection — honor `Fileset.depend`.** `backends/edam.py`
  now expands each selected fileset's declared `depend` closure (transitively, deps
  emitted before the fileset, de-duplicated, cycle-safe), for both the root target's
  filesets and a dependency's exported surface. A core can thus state exactly what a
  fileset needs (e.g. an `rtl` that depends on a `pkg` fileset) instead of relying on
  the `rtl`/`tb` naming convention alone. Files: `src/hdl_ip_packager/backends/edam.py`,
  `tests/unit/test_edam.py`.
- [x] **More tool-flow backends — Icarus Verilog, GHDL, Yosys.** Added three pure
  `Backend` implementations behind the existing `gen` interface: `IcarusBackend`
  (a `.cmd` source list + `run_iverilog.sh`), `GhdlBackend` (`run_ghdl.sh` analyze/
  elaborate/run, VHDL-only), and `YosysBackend` (a `.ys` synth script). Each rejects
  file types it can't handle and a missing top. `gen` now supports five tool flows
  (`verilator`, `vivado`, `icarus`, `ghdl`, `yosys`). Files:
  `src/hdl_ip_packager/backends/{icarus,ghdl,yosys}.py`, `backends/__init__.py`,
  `tests/unit/test_backends.py`.
- [x] **Dependabot configuration (backlog).** Added `.github/dependabot.yml` watching
  the `pip` (pyproject tooling) and `github-actions` ecosystems with weekly, grouped,
  low-noise PRs — which also surfaces action-runtime deprecations (e.g. the Node 20
  bump) automatically. File: `.github/dependabot.yml`.

  _Still open (need a live external service to build/test honestly): Git-backed and
  OCI registry backends, Sigstore (cosign) signing. Still parked (judgment): the
  `uv`/`hatch` build-backend switch (churn; `hatchling` works), source-unit
  tokenizing (large), `mutmut` (slow, unused without a run), and IP-XACT XSD
  validation (needs the bundled Accellera XSD). These land via develop and ship in
  the next release._

### Release 0.7.0 — June 2026
- [x] **Tagged `0.7.0`** per the Release plan: supply-chain (M8) — `hdlpkg pack
  --sbom` emits a deterministic CycloneDX 1.5 SBOM alongside the `.ipkg`, on top of
  the SHA-256 content addressing that already pins integrity. Shipped as `0.7.0`
  rather than `1.0.0` because the `ip.toml`/`ip.lock`/CLI formats are still pre-1.0
  and the 1.0.0 stability gate (third-party publish/consume, an `rc` soak, frozen
  formats) is not yet met; Sigstore signing remains an open issue. With M1–M8 all
  delivered, the next release boundary is `1.0.0` (a deliberate stability sign-off,
  not a feature milestone). Bumped `pyproject.toml` + `__init__.py`.

### M8 — Supply-chain: CycloneDX SBOM at pack time — June 2026
- [x] **Implemented deterministic SBOM generation (`sbom.py`) and wired `hdlpkg pack
  --sbom`.** A pure `build_cyclonedx(root, dependencies)` renders a **CycloneDX 1.5**
  JSON SBOM: the packed core as the `metadata.component`, its resolved dependency
  manifests as `components` (each with a VLNV `bom-ref`, `group`, `purl`
  `pkg:generic/...`, and licence), and the `dependencies` graph of edges. Output is
  deterministic by construction (sorted keys, components/edges sorted by VLNV, no
  timestamp or random serial number) so the same inputs pack to byte-identical SBOM
  bytes. The CLI `pack --sbom [FILE]` is the thin wrapper: it writes the SBOM
  alongside the `.ipkg` (default `<vlnv>.cdx.json`), resolving the dependency graph
  over `--search` so the SBOM pins concrete versions. Together with the SHA-256
  content addressing that already pins every artifact across the cache, lockfile,
  and registry, this delivers the *integrity + bill-of-materials* half of the
  supply-chain milestone. **Deferred** (new Open Non-Blocking Issue): Sigstore
  (cosign) keyless **signing** of the artifact + SBOM, which needs OIDC/Fulcio/Rekor
  infrastructure (or a managed key + transparency log) to build and test honestly —
  the same external-service constraint that deferred the Git/OCI backends. Exposed
  `build_cyclonedx`/`CYCLONEDX_SPEC_VERSION`. Files: `src/hdl_ip_packager/sbom.py`,
  `src/hdl_ip_packager/cli.py`, `src/hdl_ip_packager/__init__.py`, `.gitignore`,
  `tests/unit/test_sbom.py`, `tests/integration/test_sbom_cli.py`.

### Release 0.6.0 — June 2026
- [x] **Tagged `0.6.0`** per the Release plan: IP-XACT (IEEE 1685-2014) export (M7)
  — `hdlpkg export-ipxact` writes a component XML (VLNV + model views + fileSets)
  for tool interop. Bumped `pyproject.toml` + `__init__.py`.

### M7 — IP-XACT (IEEE 1685) export — June 2026
- [x] **Implemented IP-XACT export (`ipxact.py`) and wired `hdlpkg export-ipxact`.**
  A pure `to_ipxact(manifest)` renders an IEEE **1685-2014** component XML from a
  manifest: the VLNV identity, a `model` with one `view` + `componentInstantiation`
  per `[targets.*]` (carrying the target's `moduleName` and `fileSetRef`s), and the
  `fileSets` with each file's `fileType`. The manifest fileset `type` vocabulary
  (`systemVerilogSource`/`verilogSource`/`vhdlSource`) already *is* the IP-XACT
  `fileType` vocabulary, so it passes through unchanged. Built with stdlib
  `xml.etree.ElementTree` (namespaced, `ET.indent`-formatted) for deterministic,
  dependency-free output; the CLI `export-ipxact` command (removed from the planned
  stubs) is the thin wrapper that writes the XML (default
  `<vendor>.<library>.<name>.<version>.xml`). Output targets the 1685-2014 schema
  and is well-formed and structurally conventional; validating against the official
  Accellera XSD is **deferred** (new Open Non-Blocking Issue). Exposed
  `to_ipxact`/`IPXACT_NAMESPACE`. Files: `src/hdl_ip_packager/ipxact.py`,
  `src/hdl_ip_packager/cli.py`, `src/hdl_ip_packager/__init__.py`, `.gitignore`,
  `tests/unit/test_ipxact.py`, `tests/integration/test_ipxact_cli.py`,
  `tests/unit/test_cli.py`.

### Release 0.5.0 — June 2026
- [x] **Tagged `0.5.0`** per the Release plan: tool-flow generation (M6) — `hdlpkg
  gen <target>` turns a resolved design into Verilator (`.vc`) or Vivado (`.tcl`)
  inputs via a pure EDAM-like intermediate, and `hdlpkg tree` prints the resolved
  dependency graph. Bumped `pyproject.toml` + `__init__.py`.

### `hdlpkg tree` dependency view — June 2026
- [x] **Added `hdlpkg tree` to print the resolved dependency graph.** A pure
  `treeview.py` (`render_dependency_tree`) takes the root manifest, the resolver's
  one-VLNV-per-package selection, and the resolved manifests, and renders an ASCII
  tree annotating each edge with its constraint and the chosen version
  (`acme:x:mid ^1.0.0 -> 1.0.0`). A package reached twice (diamonds) is expanded
  only on first occurrence and later marked `(*)` so the output is finite;
  unresolved edges are labelled `(unresolved)`. The CLI `tree` command (removed
  from the planned list) is the thin wrapper: it resolves over `--search` against a
  `LocalDirectoryRegistry` and prints the tree. Exposed `render_dependency_tree`.
  Files: `src/hdl_ip_packager/treeview.py`, `src/hdl_ip_packager/cli.py`,
  `src/hdl_ip_packager/__init__.py`, `tests/unit/test_treeview.py`,
  `tests/integration/test_tree_cli.py`.

### M6 — Tool-flow generation (Verilator + Vivado) — June 2026
- [x] **Implemented tool-flow generation in a new `backends/` package and wired the
  real `hdlpkg gen`.** A pure, tool-agnostic EDAM-like intermediate
  (`backends/edam.py`: `EdaFile`/`EdaDesign` + `build_eda_design`) turns the root
  core plus its resolved dependencies and a chosen `[targets.*]` into a flat,
  ordered source list with a top unit and a tool flow. Selection semantics: the
  **root** contributes its target's filesets (so a `sim` target keeps its
  testbench, a `synth` target does not); a **dependency** contributes only its
  synthesizable surface (its `rtl` fileset, or all non-testbench filesets by name)
  so a dependency's testbench never leaks into a dependent. Cores are emitted
  dependencies-first via a topological sort (ties by VLNV), file types are
  normalized to the IP-XACT vocabulary, and duplicate paths are de-duplicated. Two
  `Backend` implementations consume the intermediate (`backends/base.py` interface
  + `get_backend`/`supported_toolflows` registry keyed on `toolflow`):
  `VerilatorBackend` emits a `<name>.vc` command file (`--top-module` + sources;
  rejects VHDL and a missing top), `VivadoBackend` emits a `<name>.tcl` source
  script (`read_verilog -sv`/`read_verilog`/`read_vhdl`, `set_property top`,
  `update_compile_order`). The backends are pure (`generate` returns
  `{filename: text}`); the CLI `gen` command is the thin I/O wrapper that resolves
  dependencies over `--search`, assembles the design, renders, and writes the files
  into `--output` (default `gen/<target>/`). Added `BackendError`; exposed the
  backend API from the package. Verified end to end with `hdlpkg gen sim`/`synth`
  over the bundled `examples/uart` (the FIFO dependency's rtl is pulled in, its tb
  is not). **Deferred** (now Open Non-Blocking Issues): richer dependency fileset
  selection (honor `Fileset.depend` instead of the name heuristic) and more
  backends (Icarus/GHDL/Quartus/Yosys). Files: `src/hdl_ip_packager/backends/`
  (`__init__.py`, `edam.py`, `base.py`, `verilator.py`, `vivado.py`),
  `src/hdl_ip_packager/cli.py`, `src/hdl_ip_packager/registry.py` (added
  `core_dir`), `src/hdl_ip_packager/exceptions.py`, `src/hdl_ip_packager/__init__.py`,
  `tests/unit/test_edam.py`, `tests/unit/test_backends.py`,
  `tests/integration/test_gen_cli.py`, `tests/unit/test_cli.py`.

### Release 0.4.0 — June 2026
- [x] **Tagged `0.4.0`** per the Release plan: the full producer/consumer loop — a
  deterministic `.ipkg`, append-only `publish` (with `yank`), and `pull` by VLNV —
  works against a local registry, with the cache/lockfile pinning the packed-content
  digest. Bumped `pyproject.toml` + `__init__.py`.

### M5 — `pack` / `publish` / `pull` (+ `.ipkg`, yank) — June 2026
- [x] **Implemented packaging and the distribution commands.** New `packaging.py`
  builds a **deterministic** `.ipkg` (gzip+tar of `ip.toml` + every fileset file,
  with sorted entries, fixed mode/owner, and zeroed mtime/gzip header) so a core
  always packs to byte-identical bytes and its SHA-256 is a stable content address;
  `extract_ipkg` unpacks with path-traversal protection, and `manifest_from_ipkg`
  reads the manifest back. The `.ipkg` is now the **unified artifact** across the
  stack: `Registry.artifact_bytes` returns it (the local backend packs on read, the
  HTTP backend serves `core.ipkg`), so the cache key and lockfile checksum are the
  packed-content digest (replacing the M2 manifest-bytes stopgap). A new writable
  `LocalRegistry` stores cores under `<root>/<vendor>/<library>/<name>/<version>/`
  with `ip.toml` + `core.ipkg`; publishing is **append-only** (re-publish refused)
  and `yank` drops a `.yanked` marker that hides a version from new resolves without
  breaking existing lockfiles. CLI: `pack`, `publish`, `pull` (fetch by VLNV into
  the cache, optionally extract), and `yank` (now real, removed from the planned
  stubs). Added `PackagingError`; exposed the packaging + `LocalRegistry` API.
  Verified the full pack -> publish -> pull loop end to end with matching digests.
  Files: `src/hdl_ip_packager/packaging.py`, `src/hdl_ip_packager/registry.py`,
  `src/hdl_ip_packager/cli.py`, `src/hdl_ip_packager/exceptions.py`,
  `src/hdl_ip_packager/__init__.py`, `tests/integration/test_packaging.py`,
  `tests/integration/test_pack_cli.py`, `tests/integration/test_registry.py`,
  `tests/integration/test_resolve_cli.py`, `tests/unit/test_cli.py`.

### Release 0.3.0 — June 2026
- [x] **Tagged `0.3.0`** per the Release plan: cores can now be fetched from a
  registry into a verified, content-addressed cache (M3) via local-directory and
  HTTP backends (M4), with `hdlpkg install` resolving and installing in one step.
  Bumped `pyproject.toml` + `__init__.py`. (Git/OCI registry backends remain Open
  Non-Blocking Issues.)

### M4 — Registry backends (local + HTTP) + `hdlpkg install` — June 2026
- [x] **Implemented the registry layer and wired `hdlpkg install`.** `registry.py`
  now defines the `Registry` ABC (`versions`/`manifest`/`artifact_bytes` + a shared
  `fetch` that stores a core's artifact in the content-addressed cache, and a
  default `publish` that errors until M5) plus two concrete backends:
  `LocalDirectoryRegistry` (discovers cores by scanning directory trees for
  `ip.toml`) and `HttpRegistry` (a static HTTP index:
  `{base}/{vendor}/{library}/{name}/versions.json` + `.../{version}/ip.toml`,
  fetched with stdlib `urllib`). `available_from_registry()` walks the dependency
  graph to build the resolver's input, so resolution now runs against a registry
  rather than an ad-hoc scan. The `resolve` CLI was refactored onto
  `LocalDirectoryRegistry`, and a new `install` command resolves then fetches every
  pinned core into the cache (`--cache-dir`, default `~/.hdlpkg/cache`), verifying
  each fetched digest against the lockfile (fail closed). The HTTP backend is tested
  against a localhost `http.server`. Exposed `Registry`/`LocalDirectoryRegistry`/
  `HttpRegistry`/`available_from_registry` from the package API; removed the now
  -obsolete `test_planned_stubs.py`. A core's "artifact" is its manifest bytes until
  M5 packaging defines the packed form (the interface is unchanged by that).
  **Deferred** (now Open Non-Blocking Issues): the **Git-backed** and **OCI
  artifact** registry backends — both need external tooling / a live service to
  build and test, so they could not land honestly within this milestone. Files:
  `src/hdl_ip_packager/registry.py`, `src/hdl_ip_packager/cli.py`,
  `src/hdl_ip_packager/__init__.py`, `tests/integration/test_registry.py`,
  `tests/integration/test_resolve_cli.py`, `tests/unit/test_cli.py`.

### M3 — Content-addressed cache — June 2026
- [x] **Implemented the content-addressed local cache (`cache.py`).**
  `ContentAddressedCache` is a blob store keyed by the SHA-256 of each blob's own
  bytes, sharded git-style (`<root>/sha256/ab/cdef...`). The defining property is
  **verify-on-read**: `get()` recomputes the digest and raises `RegistryError` if
  it disagrees with the requested key, so a corrupted or tampered blob fails closed
  instead of poisoning a build. `put()` is atomic (temp file + `os.replace`) and
  idempotent (content-addressing dedupes); `has()`/`path_for()` round out the
  surface, and digests are validated against the canonical `sha256:<hex>` form.
  `default_cache_root()` returns a user-level dir (`~/.hdlpkg/cache`) so cores are
  reused across projects offline. Reused `lockfile.sha256_digest` and the existing
  `RegistryError` rather than adding a type. The store is standalone this milestone;
  M4's registry backends fetch into it and M5's packaging defines blob contents.
  Exposed `ContentAddressedCache`/`default_cache_root` from the package API. Files:
  `src/hdl_ip_packager/cache.py`, `src/hdl_ip_packager/__init__.py`,
  `tests/integration/test_cache.py`.

### Release 0.2.0 — June 2026
- [x] **Tagged `0.2.0`** per the Release plan: the first release where the tool does
  its core job — resolve a dependency graph (M1) to a deterministic, verifiable
  `ip.lock` (M2) via `hdlpkg resolve`. Bumped `pyproject.toml` + `__init__.py`.

### M2 — Lockfile (`ip.lock`) + `hdlpkg resolve` — June 2026
- [x] **Implemented the lockfile model and wired `hdlpkg resolve`.** New pure
  `lockfile.py`: `LockedPackage` (vlnv + source + checksum) and `Lockfile`
  (`from_resolution`, `to_toml`/`from_toml`/`from_path`, `verify`,
  `matches_resolution`). The file is TOML with a schema `version` and a
  `[[package]]` array sorted by VLNV, so it is deterministic and diff-friendly;
  `from_toml(to_toml(x)) == x` round-trips, and `verify` fails closed on a missing
  or mismatched checksum. A `sha256_digest(bytes)` helper gives the canonical
  `sha256:<hex>` form. The `resolve` CLI command (now real, removed from the
  planned stubs) loads the root manifest, discovers candidate cores by scanning
  `--search` directories for `ip.toml` (a stopgap until M4's registry backends),
  runs the resolver, and writes `ip.lock` next to the manifest. The recorded
  checksum currently digests the manifest bytes; M3 widens it to full packaged
  content without changing the format. Exposed `Lockfile`/`LockedPackage`/
  `sha256_digest`/`LockfileError` from the package API and added `LockfileError` to
  the hierarchy. Verified end to end on the bundled `examples/` (UART resolves the
  FIFO dep). Files: `src/hdl_ip_packager/lockfile.py`,
  `src/hdl_ip_packager/cli.py`, `src/hdl_ip_packager/exceptions.py`,
  `src/hdl_ip_packager/__init__.py`, `tests/unit/test_lockfile.py`,
  `tests/integration/test_resolve_cli.py`, `tests/unit/test_cli.py`.

### M1 — Dependency resolver — June 2026
- [x] **Implemented the dependency resolver (`resolver.py`).** `resolve(root,
  available)` turns the root manifest plus `available: Mapping[PackageRef,
  Sequence[Manifest]]` (the manifests of each package's known versions) into a
  `Resolution` = one concrete `Vlnv` per package. Algorithm: backtracking search
  that picks the **newest** version satisfying every accumulated constraint,
  follows each chosen candidate's own `[dependencies]` transitively, intersects
  constraints on shared packages (diamonds), and falls back to older versions when
  a newest-first choice makes a transitive constraint unsatisfiable. **Single
  version per package**, fail-on-conflict (HDL can't elaborate two versions of a
  module); pre-releases are excluded unless a constraint's operand is itself a
  pre-release of the same core (reusing the `VersionConstraint` rule). The module
  is pure (no I/O) — `available` is supplied by the caller, so a registry (M4) can
  feed it later without changing the contract; `ResolutionError` names the
  offending package, its constraints, and the versions on offer. Chose to key
  `available` on full manifests rather than bare versions so transitive deps are
  reachable without a separate lookup. Exposed `Resolution` + `resolve` from the
  package API. The `resolve` CLI command stays a planned stub until M2 (lockfile)
  gives it something to write. Files: `src/hdl_ip_packager/resolver.py`,
  `src/hdl_ip_packager/__init__.py`, `tests/unit/test_resolver.py`,
  `tests/unit/test_planned_stubs.py`.

### Release plan + first tag (0.1.0) — June 2026
- [x] **Defined the pre-1.0 release plan and cut `0.1.0`.** Added a "Release plan"
  section to this tracker: `0.MINOR.PATCH` while pre-1.0 (MINOR = capability
  milestone and may break formats; PATCH = fixes; `-rc.N` for risky cuts), with the
  insight that the SemVer contract here is the on-disk `ip.toml` / `ip.lock` formats
  + CLI rather than the Python API. Releases are cut at capability boundaries, so
  milestones are grouped into six minor releases (0.1 foundation, 0.2 = M1+M2,
  0.3 = M3+M4, 0.4 = M5, 0.5 = M6, 0.6 = M7) with `1.0.0` reserved for M8 *plus* an
  explicit stability commitment (frozen formats, stable CLI/registry protocol, a
  third-party publish/consume, and an rc soak). Bumped the package to `0.1.0`
  (`pyproject.toml`, `__init__.py`) and tagged it as the first release and a
  low-stakes shakedown of the new `release.yml` pipeline. Files:
  `docs/progress_tracker.md`, `pyproject.toml`, `src/hdl_ip_packager/__init__.py`.

### Release automation (tag -> PyPI) — June 2026
- [x] **Added a tag-driven PyPI release workflow.** New
  `.github/workflows/release.yml` fires on an `X.Y.Z` (or `X.Y.Z-rc.N`) tag, builds
  the wheel + sdist with `python -m build`, and publishes them to PyPI via OIDC
  "trusted publishing" (`pypa/gh-action-pypi-publish`, `id-token: write`, a `pypi`
  environment) so no API token is stored in the repo. The build job first runs a
  new `scripts/check_release_version.py` guard that fails the release if the git
  tag disagrees with `[project].version` in `pyproject.toml`, preventing a
  mislabelled artifact. The guard's comparison logic is pure (it takes the ref and
  the `pyproject.toml` text as arguments) and unit-tested in
  `tests/unit/test_check_release_version.py`; only its `main` touches the
  environment/filesystem. Both files are stdlib-only (`tomllib`). One-time setup is
  required on PyPI (register the repo + workflow as a trusted publisher and create
  the `pypi` environment). Files: `.github/workflows/release.yml`,
  `scripts/check_release_version.py`, `tests/unit/test_check_release_version.py`.

### Property-based tests (Hypothesis) — June 2026
- [x] **Added Hypothesis property tests for `version.py`.** New
  `tests/unit/test_version_properties.py` asserts the invariants that must hold for
  every input, complementing the example-based `test_version.py`: the parse/render
  round-trip (`Version.parse(str(v)) == v` and exact string round-trip), that
  ordering is a genuine total order (trichotomy + antisymmetry) and that `sorted`
  agrees with it, that a constraint built from a version contains/excludes that
  version per its operator (`^`/`~`/`=`/`>=`/`<=` include, `>`/`<` exclude, and `^`
  excludes the next major), and grammar fuzzing that `Version.parse` /
  `VersionConstraint.parse` only ever raise their declared error type on arbitrary
  text. A shared `settings(max_examples=60, deadline=None)` keeps the loop fast and
  sidesteps wall-clock-per-example flakiness on the AV-throttled paths noted in
  `CLAUDE.md`. Added `hypothesis` to the `dev` extra. Files:
  `tests/unit/test_version_properties.py`, `pyproject.toml`.

### Pre-commit hooks — June 2026
- [x] **Added `.pre-commit-config.yaml` mirroring the CI gates.** Contributors can
  now run `pre-commit install` to catch ruff (lint + format) and mypy (strict on
  `src/`) failures on `git commit`, before CI. The mypy hook uses
  `pass_filenames: false` + `args: [src]` so it always checks the whole library
  tree exactly as CI does, rather than per-file fragments; tool rules stay in
  `pyproject.toml` and the pinned hook revs track the floors in the `dev` extra.
  Also wired standard hygiene hooks (trailing-whitespace, end-of-file-fixer,
  check-yaml/-toml, check-merge-conflict, check-added-large-files). Added
  `pre-commit` to the `dev` extra and a `tests/unit/test_precommit_config.py`
  integrity test that parses the config and asserts the CI-mirroring hooks are
  present (so a typo can't silently disable the local gates). Files:
  `.pre-commit-config.yaml`, `pyproject.toml`, `tests/unit/test_precommit_config.py`.

### Coverage gate ratchet — June 2026
- [x] **Raised the coverage `fail_under` gate from 85 to 93.** With the implemented
  surface now larger (and the `init` scaffolder added), the suite sits at ~96%, so
  the old 85 floor no longer protected against regressions. Bumped `fail_under` to
  93 in `[tool.coverage.report]`, keeping a small buffer below the live number so a
  feature whose tests land in the same change is never tripped by a transient
  partial branch. Also closed the last gaps in `cli.py` by covering the `init`
  command's interactive-prompt path (both a successful prompt and a blank-answer
  failure), via `monkeypatch` on `sys.stdin.isatty` + `builtins.input`. Files:
  `pyproject.toml`, `tests/unit/test_cli.py`.

### `hdlpkg init` scaffolder — June 2026
- [x] **`hdlpkg init` scaffolds a starter `ip.toml`.** Added a pure `scaffold.py`
  module: a frozen `ScaffoldOptions` value type (identity validated by reusing
  `PackageRef`/`Version`, `top` defaulting to the core name) and a `render_manifest`
  function that emits a complete, valid manifest with one `rtl` fileset and one
  `sim` target. The renderer is deliberately I/O-free and its output round-trips
  through `Manifest`, so a freshly scaffolded core passes `hdlpkg validate`
  immediately; a unit test asserts that invariant. The CLI `init` command (now a
  real command, removed from the planned-stub list) is the thin I/O wrapper: it
  takes `--vendor/--library/--name/--version/--description/--license/--top` flags
  plus an optional target directory, prompts for the three required identity fields
  only when stdin is a TTY (so CI/tests never block), refuses to overwrite an
  existing `ip.toml` unless `--force` is given, and writes the file. Rationale: a
  low-effort, high-value DX win that lets authors start a core without copying an
  example by hand, and it lands cleanly before the M1 resolver. Files:
  `src/hdl_ip_packager/scaffold.py`, `src/hdl_ip_packager/cli.py`,
  `tests/unit/test_scaffold.py`, `tests/unit/test_cli.py`.

### Examples and developer experience — June 2026
- [x] **Documentation site (MkDocs Material -> GitHub Pages).** Added `mkdocs.yml`
  (Material theme, light/dark toggle, search, the `docs/` tree as nav) and a `docs`
  optional-dependency group (`mkdocs-material`). A new `.github/workflows/docs.yml`
  builds the site and publishes it to GitHub Pages on push to `main` using the
  official Pages flow (`upload-pages-artifact` + `deploy-pages`, with
  `pages: write` + `id-token: write` and a `pages` concurrency group); it requires
  the repo's Pages source set to "GitHub Actions". The config is deliberately kept
  free of `!!python/name:` tags so `tests/unit/test_docs_site.py` can `safe_load`
  it and assert every `nav` page exists, catching a renamed/removed doc before it
  breaks the published site (`pyyaml` added to the dev extras for that test). Cross
  -repo links to `src/` and root files render as build warnings (not errors) via
  the `validation` settings, so a plain `mkdocs build` stays green; making those
  links resolve on the site is deferred. Files: `mkdocs.yml`,
  `.github/workflows/docs.yml`, `pyproject.toml`, `tests/unit/test_docs_site.py`,
  `.gitignore`.
- [x] **Bundled example IP cores under `examples/`.** Added two real cores with
  valid `ip.toml` manifests: `acme:common:fifo:1.0.0` (a synchronous FWFT FIFO,
  leaf) and `acme:comm:uart:1.2.0` (an 8N1 UART whose receive path buffers bytes
  in the FIFO, so it declares `"acme:common:fifo" = "^1.0.0"`). Together they form
  a minimal self-contained two-node dependency graph that will exercise the
  resolver (M1) once it lands. Each core ships small synthesizable SystemVerilog
  (`rtl/`) plus a smoke testbench (`tb/`) so every fileset path resolves to a real
  file. A new `tests/integration/test_examples.py` guards three properties in CI:
  every manifest validates (via `Manifest` and the `hdlpkg validate` path), every
  fileset-referenced file exists on disk, and every `acme` dependency points at
  another bundled example. Rationale: gives the docs concrete cores to point at
  and replaces inline-only fixtures with on-disk manifests, catching schema drift
  and dangling source paths automatically. Files: `examples/`, `examples/README.md`,
  `tests/integration/test_examples.py`.

### Project bootstrap — June 2026
- [x] **Repository, Python project scaffolding, and conventions established.**
  Created the project structure mirroring the reference project's git/docs/AI
  conventions: `README.md`, `.gitignore`, `.gitattributes`, `LICENSE` (MIT),
  `CLAUDE.md`, and the `docs/` set (this tracker, `architecture.md`,
  `ai_agent_instructions.md`, `INDEX.md`, `README.md`, `research/state_of_the_art.md`).
  Set up a `src/`-layout Python package with `pyproject.toml` (hatchling backend,
  `hdlpkg` entry point) and the dev toolchain (pytest, ruff, mypy) configured in
  one file. Files: repo root, `docs/`, `pyproject.toml`.
- [x] **Foundation modules implemented + tested.** `version.py` (SemVer 2.0.0 +
  constraint grammar), `vlnv.py` (VLNV identity), `manifest.py` (`ip.toml`
  parse/validate), `exceptions.py` (error hierarchy), `cli.py` (`hdlpkg`
  `info`/`validate` + wired planned commands), and planned-subsystem seams
  (`resolver.py`, `registry.py`). 108 tests pass, ~96% coverage; ruff + mypy(strict
  on src) clean. Files: `src/hdl_ip_packager/*`, `tests/*`.
- [x] **Scalable test framework + reporting.** Marker-based pytest layout
  (`unit`/`integration`/`slow`), shared fixtures + a local per-module summary in
  `conftest.py`, coverage gate, and `scripts/render_test_summary.py` that turns
  JUnit XML into a foldable GitHub step summary (cross-platform, stdlib-only).
  Files: `tests/`, `scripts/render_test_summary.py`, `pyproject.toml`.
- [x] **CI pipeline.** GitHub Actions workflow runs the suite on push/PR across
  Python 3.11/3.12, enforces ruff + mypy, and renders the test summary. Files:
  `.github/workflows/ci.yml`.
- [x] **State-of-the-art research captured.** Surveyed software package managers
  (pip/npm/Cargo/Go/Conda/Docker-OCI) and HDL tools (IP-XACT, FuseSoC, Bender,
  Orbit, hdlmake, Vivado IP Packager); recorded findings, a comparison table, and
  the nine design decisions they drive. File: `docs/research/state_of_the_art.md`.

---

## Archive

_Empty — the project is new._
