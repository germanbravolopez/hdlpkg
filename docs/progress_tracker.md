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

**Version**: **`1.0.0-rc.1`** cut — the first 1.0 release candidate, published to PyPI as a
**pre-release** to start the **soak** (no `ip.toml`/`ip.lock`/CLI/registry-protocol change
until promotion). It carries everything that landed since `0.8.0`: the **versioning contract
for the 1.0 freeze** — Cargo-style unification, a `[resolution] on-conflict` policy
(`fail_on_conflict` default / `use_latest` / `isolate_namespaces`) that allows
multi-version coexistence in the resolve/lock/tree (with `gen` refusing two versions),
and the `[package].scheme` key (`semver` / `opaque`) with explicit non-SemVer
rejection, **and the operational distribution protocol** — HTTP + OCI registry backends
behind one `registry_from_location` abstraction, with `hdlpkg login` auth (direct bearer
**and** the OCI token-exchange, reusing `docker login`) for private, self-hosted registries.
With the resolver contract, the `ip.toml`/`ip.lock` format shapes, and the registry/OCI
protocol now settled, the path to the final `1.0.0` is just the soak: the **`1.0.0-rc.1`
soak is now underway** (this candidate must hold with no format/CLI/protocol change), and a
**third-party publish/consume** should validate this rc during the soak. A clean soak is
promoted to `1.0.0`; any required format change resets it (and would ship as `0.9.0`). See
the Release plan.

**Stage**: Feature-complete for the roadmap (M1–M8) plus the pre-1.0 completeness
pass; fully typed, linted, and tested (457 passing tests, ~95% coverage):
- **Versioning** — SemVer 2.0.0 `Version` + `VersionConstraint` (caret/tilde/range
  grammar, pre-release precedence).
- **Identity** — `PackageRef` and `Vlnv` (`vendor:library:name:version`).
- **Manifest** — `ip.toml` parsing/validation (`[package]`, `[dependencies]`,
  `[filesets]`, `[targets]`), with an optional `schema` version for a migration path.
- **Resolver** — backtracking, newest-compatible dependency resolution that unifies
  SemVer-compatible dependents (Cargo-style) and applies a configurable
  `[resolution] on-conflict` policy to an incompatible conflict
  (`fail_on_conflict`/`use_latest`/`isolate_namespaces`, the last keeping multiple
  versions per package); scheme-aware (`semver`/`opaque`); pure, fed by an in-memory
  version index.
- **Lockfile** — deterministic `ip.lock` (serialize/parse/verify a `Resolution`
  with per-core source + SHA-256), written by `hdlpkg resolve`.
- **Cache** — content-addressed local blob store (SHA-256 key, verify-on-read,
  atomic writes), populated by `hdlpkg install`.
- **Registry** — `Registry` interface + local-dir/writable-local/HTTP/OCI backends
  behind one `registry_from_location` scheme dispatch (path / `http(s)://` / `oci://`),
  all writable (append-only + yank), + a dependency-graph walker feeding the resolver
  (Git backend is an open Non-Blocking issue).
- **Credentials** — per-host `Credential` (direct bearer or username+secret) for private
  registries via `hdlpkg login`; OCI token-exchange (401 -> realm -> scoped access token);
  `~/.docker/config.json` reused as a fallback.
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
  `install`/`pack`/`publish`/`pull`/`yank`/`login`/`logout`/`gen`/`tree`/`export-ipxact`.
  `install --locked` and `gen --locked` give reproducible, lockfile-driven builds.
- **Tooling** — pytest (markers + coverage gate + foldable summary), ruff, mypy
  strict on `src/`, CI workflow, and a cross-platform test-summary renderer.

**Next**: all roadmap milestones (M1–M8) are delivered, the versioning contract that was
gating the format freeze is settled (ordered non-SemVer schemes + SV/VHDL package
name-mangling), and the **registry/OCI protocol is now implemented** — local, HTTP, and OCI
backends behind one abstraction, with `hdlpkg login` auth for private self-hosted sharing.
The OCI **token-exchange** auth flow now also ships (managed Harbor/cloud registries work,
plus `docker login` reuse). The remaining work toward `1.0.0` is the narrow stability gate
(see the Release plan) — a third-party publish/consume and a `1.0.0-rc.1` soak — plus
still-deferred external-service work (Git-backed registry, Sigstore signing) and the
residual coexistence case (two *module*/*entity* versions — needs an HDL-aware frontend;
package coexistence is done for both SystemVerilog and VHDL).

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
| Full compile/elaborate/simulate of the consumer demo's SV + VHDL outputs | consumer demo (`verify.py`, `demo.py`, `.github/workflows/verify.yml`), `backends/` | **Strengthen the end-to-end proof.** Today the consumer demo (and the in-repo `gen` tests) only assert that `gen` *emits* the right tool-flow inputs (`.vc`/`run_ghdl.sh`/mangled sources); nothing actually **builds** them. Add a real toolchain pass that compiles, elaborates, and simulates the generated designs — `verilator`/`icarus` for the SystemVerilog SoCs (`soc/`, `soc_conflict/`) and `ghdl` for the VHDL one (`soc_vhdl/`) — so we prove the generated flows genuinely elaborate (and that the package name-mangling produces designs that *build*, not just text that looks right). Needs the HDL toolchains installed on the runner (e.g. `ghdl`, `verilator`/`iverilog` via apt or a setup action), so it is a separate, possibly opt-in CI lane from the pure-Python `verify` matrix. This feeds the 1.0 **third-party consume** confidence but does not itself gate the release. |
| Encrypted IP distribution (IEEE 1735) | `packaging.py`, `registry.py`, `manifest.py`, `cli.py` | **Future feature.** Let a producer distribute a core whose HDL source is **encrypted**, so a consumer can resolve/install/`gen` against it (the tool can drive a tool flow) without the source ever being readable on disk. Two distinct layers, decide which to build: **(a) Standard HDL IP encryption (IEEE 1735 / `pragma protect`)** — the cross-vendor norm. Each source file carries an encrypted envelope (a symmetric session key wrapped under each *tool vendor's* public key + AES/RSA-encrypted payload, IEEE 1735 v1/v2 with "rights" digests). The EDA tool decrypts at compile time; the packager's job is to **carry, not break** these envelopes — pack/`extract`/SBOM must treat an encrypted file as opaque, the deterministic-pack digest still pins ciphertext, and `gen` must not assume it can read the source. The tool would *not* implement the crypto itself (vendor keys live in the EDA tools); at most it could shell out to `vivado -encrypt`/`vlog +protect` to *produce* envelopes. **(b) At-rest/transport encryption of the `.ipkg`** — encrypt the whole artifact in the registry/cache for confidential distribution (e.g. age/GPG or an OCI-layer key), decrypted on `pull` with a consumer key. This is independent of HDL-tool semantics and simpler, but does **not** give the per-tool, compile-time protection (a) does. Open questions: where keys/recipients are declared (a `[package]`/`[encryption]` manifest key vs. out-of-band), how it interacts with content-addressing (the digest must pin what is *stored*), how the SBOM marks a component encrypted, and how `validate`/`info` behave when source is unreadable. Needs a real EDA tool (or an interop fixture) to test (a) honestly — defer like the Git/OCI/Sigstore work. |
| Git-backed registry | `registry.py` | A `Registry` backend resolving cores from a Git channel (tags/refs). Deferred from M4: needs the `git` CLI + a remote to implement and test honestly. Mirror the `LocalDirectoryRegistry`/`HttpRegistry`/`OciRegistry` shape. |
| Sigstore (cosign) artifact signing | `packaging.py`, `.github/workflows/` | The unbuilt half of M8: keyless signing of the `.ipkg` + SBOM and a verify path. Needs OIDC + Fulcio/Rekor (or a managed key) and a live transparency log to implement and test honestly — deferred like the Git backend. Checksums + SBOM already ship; this adds authenticity on top. |
| `gen` straight from a registry | `cli.py`, `registry.py` | `resolve`/`install`/`tree --registry` now consume **local, HTTP, and OCI** registries directly (the producer->consumer loop is closed over the network). Remaining: a fetch-then-extract path so `gen` can build straight from a registry — it still needs loose sources via `--search` (point it at extracted/`pull`ed trees). |
| Validate IP-XACT against the official XSD | `ipxact.py`, tests | M7 emits well-formed, structurally-conventional 1685-2014 XML but does not validate against the Accellera XSD. Add an (optional, dev-only) schema-validation test (e.g. `xmlschema`) so structural drift is caught; consider IP-XACT 2022 and richer mapping (bus interfaces, parameters). |
| Multi-version coexistence for *modules*/*entities* (beyond packages) | `mangle.py`, `cli.py` | **Package** coexistence is done for both SystemVerilog and VHDL (`gen` name-mangles under `isolate_namespaces`). What remains: two versions of a SystemVerilog *module*/interface or a VHDL *entity*. Unlike a package reference (`::` / `use work.`), an *instantiation* position (`foo bar (...)` in SV, `label : entity work.foo` / component instantiation in VHDL) cannot be disambiguated from other constructs without a real parser, so it is refused today. Needs an HDL-aware frontend (cf. the parked "source-unit tokenizing" backlog item). |

---

## Backlog (deferred — low value / not currently planned)

| Issue | Why parked |
|-------|------------|
| Switch build backend setuptools→`uv`/`hatch` workflow tooling | `hatchling` backend already works and is PEP-compliant; revisit only if the team standardizes on `uv` end to end. |
| Source-unit tokenizing (auto-discover HDL deps like Orbit) | Powerful but large; only worth it after the manifest-driven flow (M1–M5) is solid. |
| Mutation testing (`mutmut`) | Validates test quality, but slow and only worth it once the implemented surface is larger. |

---

## Completed Milestones

### Release 1.0.0-rc.1 — June 2026
- [x] **Cut `1.0.0-rc.1`, the first 1.0 release candidate**, to **start the soak** toward the
  final `1.0.0`. It bundles everything since `0.8.0`: the versioning contract for the 1.0
  freeze (Cargo-style unification, the `[resolution] on-conflict` policy, SV+VHDL package
  name-mangling, ordered non-SemVer schemes), and the operational distribution protocol
  (local/HTTP/OCI registries behind `registry_from_location`, `hdlpkg login` with direct
  bearer **and** OCI token-exchange + `docker login` reuse). Published to PyPI as a
  **pre-release** (PEP 440 `1.0.0rc1`), so `pip install hdl-ip-packager` does not pick it up
  unless `--pre`/an explicit pin is used; `release.yml` marks the GitHub release pre-release.
  Bumped `pyproject.toml` + `__init__.py` to `1.0.0-rc.1`. **The soak rule**: this candidate
  must hold with **no `ip.toml`/`ip.lock`/CLI/registry-protocol change**; a clean soak (ideally
  including a genuine third-party publish/consume against this rc) is promoted to `1.0.0`, while
  any required format change resets the soak and ships as `0.9.0` instead. Promotion to `1.0.0`
  remains a deliberate, human-gated sign-off (not autonomous).

### OCI token-exchange auth flow (works against managed Harbor/cloud registries) — June 2026
- [x] **`OciRegistry` now performs the Docker/OCI token-exchange dance**, so it
  authenticates against registries that issue short-lived access tokens (managed Harbor,
  GitLab, Docker Hub, ECR/ACR), not only ones that accept a static bearer. On a `401`
  carrying `WWW-Authenticate: Bearer realm=...,service=...,scope=...`, the backend calls
  the realm token endpoint (HTTP Basic with the stored credential, or anonymously for a
  public pull token), caches the returned access token, and retries the request once.
  Because the retry happens per request using the server-supplied scope, a pull-scoped
  token is transparently upgraded to a push scope when publishing. A username-less
  credential is still sent directly as a bearer (the self-hosted/no-auth path that
  already worked is unchanged). New pure helper `parse_bearer_challenge` (unit-tested).
- [x] **Credentials grew a username.** `Credential(secret, username=None)` replaces the
  bare token: a username-less credential is a direct bearer; a username+secret pair is
  used as HTTP Basic in the exchange. `hdlpkg login` gained `--username` (and `--password`
  as an alias of `--token`), prompting for a password instead of a token when a username
  is given. The credentials file moved to a richer `[registries."host"]` form (with an
  optional `username`), and **still reads the legacy `[tokens]` table** so older files
  keep working.
- [x] **`docker login` credentials are reused.** `~/.docker/config.json`
  (`$DOCKER_CONFIG` honored) is parsed for `auths[host].auth` (base64 `user:pass`) and
  `identitytoken`, and merged as a **fallback** under stored `hdlpkg login` credentials,
  so a registry the user already authenticated with Docker works without a second login.
- [x] **Tested honestly with no live service**: a localhost mock that *requires* the
  exchange (401 challenge -> a Basic-checking token endpoint -> bearer-gated `/v2/`)
  drives the full publish/resolve flow via the CLI, plus wrong-password failure and an
  anonymous pull-only token (resolve works, push is refused); the challenge parser,
  `Credential`/docker-config parsing, and the store round-trip have unit tests. Files:
  `credentials.py`, `registry.py`, `cli.py`, `__init__.py`, `tests/unit/test_credentials.py`,
  `test_registry_location.py`, `test_login_cli.py`, `tests/integration/test_oci_auth_cli.py`.
  Validated earlier against live no-auth Zot and `docker run registry:2`; this closes the
  authenticated-registry gap noted then.

### Stable registry protocol: HTTP + OCI backends behind one abstraction, with login auth — June 2026
- [x] **Network registries are now first-class, so teams can share IP privately on their
  own servers** — the operational half of the 1.0 "stable registry/OCI protocol" gate.
  `resolve`/`install`/`tree`/`publish`/`pull` accept a `--registry` **location** dispatched
  by URL scheme through a single `registry_from_location()` factory: a bare path / `path:` /
  `file://` -> the writable local `LocalRegistry`, `http(s)://` -> `HttpRegistry`, and
  `oci://` / `oci+http://` -> the new `OciRegistry`. The CLI is now backend-agnostic (the
  one place a backend is chosen is the factory), which is what makes the on-disk and wire
  protocol surface stable for 1.0.
- [x] **`OciRegistry`: cores as OCI artifacts over the OCI distribution v2 API**, so a core
  lives in any standard registry (Harbor, Artifactory, Nexus, GitLab, Zot, ECR/ACR) — all of
  which are **self-hostable and private by default**. A core's `ip.toml` is the artifact
  *config* blob and its deterministic `.ipkg` is the single *layer*, tagged with the version;
  the package maps to repository `{prefix}/{vendor}/{library}/{name}`. Implements blob upload
  (HEAD-skip + POST/PUT monolithic), manifest/tag PUT+GET, and `tags/list`, append-only
  (refuses to overwrite a tag). `oci://` uses HTTPS, `oci+http://` plaintext (internal/dev).
  Because the layer is the `.ipkg`, its OCI digest **is** the content address the cache keys
  on and the lockfile pins.
- [x] **`HttpRegistry` promoted to a writable, authenticated network registry** (was a
  read-only static index): reads via `GET`, publishes via `PUT` (so any `PUT`-capable store —
  a small service, object storage, WebDAV — can host it), append-only, opaque-version tolerant.
- [x] **`hdlpkg login` / `logout` + a credentials subsystem (`credentials.py`)** make the
  network backends private. A pure `CredentialStore` maps a **registry host** to a bearer
  token (hosts share one token across repos) with TOML serialization; the thin
  `load_credentials`/`save_credentials` pair is the only I/O, writing
  `~/.hdlpkg/credentials.toml` (override with `HDLPKG_CREDENTIALS`) owner-only where the OS
  allows. Every network request carries `Authorization: Bearer <token>`, so resolve/install/
  publish against a private registry "just work" after one login; missing/wrong credentials
  fail closed. (The Docker token-exchange flow for managed registries is a tracked refinement;
  the stored token is presented directly today.)
- [x] **Tested honestly with no live service**: a localhost auth+`PUT` HTTP server and a
  minimal in-memory **OCI distribution v2** mock exercise the full publish -> resolve ->
  install -> pull flow through the real CLI for both backends, plus append-only, auth-required,
  and error paths; the `CredentialStore`, `registry_from_location` dispatch, and `login`/
  `logout` have unit tests. Files: `src/hdl_ip_packager/credentials.py`, `registry.py`,
  `cli.py`, `exceptions.py` (`CredentialsError`), `__init__.py`,
  `tests/unit/test_credentials.py`, `test_registry_location.py`, `test_login_cli.py`,
  `tests/integration/test_http_registry_cli.py`, `test_oci_registry_cli.py`. Remaining toward
  1.0: a third-party publish/consume and a `1.0.0-rc.1` soak (see the Release plan); Git
  backend, the OCI token-exchange flow, and `gen`-from-registry stay Open Non-Blocking.

### VHDL package name-mangling for multi-version coexistence — June 2026
- [x] **`gen` now name-mangles coexisting VHDL packages too**, the direct analogue of
  the SystemVerilog-package work, so two versions of a shared VHDL package build
  together under `[resolution] on-conflict = "isolate_namespaces"` (e.g. via the `ghdl`
  toolflow). A new VHDL-aware lexer (`mangle.py`) — case-insensitive, `--`/`/* */`
  comment- and string-aware — rewrites a package name only in the unambiguous VHDL
  positions: `package <name>` / `package body <name>` declarations, `end [package
  [body]] <name>` labels, and `use work.<name>...` references. Each consumer's `use`
  clause is routed to the version it resolved to (`vfifo` -> `vbus__v1_1_0`,
  `vlegacy` -> `vbus__v2_0_0`). VHDL's reference contexts are structured (`use`/`work.`),
  so this is as safe as the SV-package case — no full parser.
- [x] **The mangler became language-aware.** `GenSourceFile` now carries a `language`
  (from the fileset type) instead of an SV-only flag; `plan_package_mangling` dispatches
  declared-name scanning and rewriting per language, and **refuses** what it cannot do
  safely: a colliding *module*/interface (SV) or *entity* (VHDL) — instantiation
  position is ambiguous without a real parser — or an unknown source language. Named-
  library `use` clauses (anything other than `work.`) are left untouched (a documented
  limitation; everything is analyzed into `work`). New: `declared_vhdl_packages`,
  `declared_vhdl_entities`, `rewrite_vhdl_packages`. Verified end to end against the
  consumer demo's new VHDL `soc_vhdl` (a `vbus` package at two majors, `ghdl` flow).
  Files: `mangle.py`, `cli.py`, `backends/edam.py`, `resolver.py` (warning text),
  `__init__.py`, `tests/unit/test_mangle.py`,
  `tests/integration/test_mangle_vhdl_gen_cli.py`.

### Physical multi-version coexistence at `gen`: SystemVerilog package name-mangling — June 2026
- [x] **`gen` now builds two versions of one SystemVerilog *package* together** instead
  of refusing — the physical half of multi-version coexistence. Under `[resolution]
  on-conflict = "isolate_namespaces"` (the policy that keeps incompatible versions),
  `gen` automatically **name-mangles** each package version to a unique name
  (`bus_pkg` -> `bus_pkg__v1_1_0` / `bus_pkg__v2_0_0`) and rewrites every consumer's
  references to the version *it resolved to* (`fifo` -> `__v1_1_0`, `legacy` ->
  `__v2_0_0`), so both elaborate in HDL's one global namespace. The rewritten sources
  are materialized into `<output>/src/<vlnv>/…` and the generated tool file points at
  those copies; the originals on disk are untouched. Verified end to end against the
  external consumer demo's `soc_conflict/`.
- [x] **Safe by construction, no full parser.** A new pure `mangle.py` carries a
  comment/string-aware SystemVerilog scanner that rewrites a package name only in the
  syntactically **unambiguous** positions — `package <name>` / `endpackage : <name>`
  declarations, `import <name>::`, and `<name>::` scoped references — so a coincidental
  signal named `bus_pkg`, or the name inside a comment or string, is never touched. The
  pure `plan_package_mangling` computes per-file rename maps (a package's own
  declaration vs a consumer's resolved version) and **refuses** what it cannot do
  safely: two versions of a *module*/interface (instantiation position is ambiguous
  without parsing) or any non-SystemVerilog (VHDL) source — those still get a clear
  `BackendError`. Documented limitation: a macro that *constructs* a package name by
  token pasting is left untouched. Files: `mangle.py`, `backends/edam.py`
  (`build_eda_design(allow_multiversion=…)` + multi-version-safe topo sort), `cli.py`
  (`gen` materializes the mangled tree, warns, reports), `__init__.py`,
  `tests/unit/test_mangle.py`, `tests/integration/test_mangle_gen_cli.py`. (Remaining:
  module/interface coexistence and VHDL — both deferred as needing a real HDL frontend.)

### Ordered non-SemVer schemes: CalVer + monotonic — June 2026
- [x] **Added two ordered non-SemVer version schemes behind `[package].scheme`** so
  such cores can be *ranged* and newest-selected, not just exact-pinned. `scheme =
  "calver"` carries ordered numeric date/calendar versions (`2024.1`, `2024.10`,
  `2025.2.3`) with the **first component (year) as the compatibility boundary**:
  `^2024.1` == `>=2024.1, <2025`, `~2024.1` == `>=2024.1, <2024.2`, and same-year
  dependents unify (year-as-major, Cargo-style). `scheme = "monotonic"` carries a
  single ordered revision (`r3`, `rev12`, `12`); all revisions are **one
  compatibility group** (newer supersedes), so `^r3` == `>=r3` selects the newest
  while `~r3`/`=r3` pin exactly. Two distinct exact monotonic pins are a hard
  unsatisfiable failure (one shared group), not a coexistence.
- [x] **Implementation**: new ordered `CalVer` and `MonotonicVersion` value types and
  a `parse_version(text, scheme)` dispatcher in `version.py`; `VersionConstraint`
  gained a *deferred* ordered-clause path (`ordered`) that interprets `^`/`~`/ranges
  against the candidate's scheme at match time (the dependency's scheme is unknown at
  parse) — for non-SemVer schemes a **bare** constraint means *exact* (those schemes
  lack SemVer's caret default; use `^`/`~`/ranges explicitly). `compatibility_group`,
  the resolver's `_edge_node` grouping, manifest/`Vlnv` parsing, and the lockfile
  `scheme` marker all extend to the new schemes; `LocalRegistry.versions` already
  recovers a non-SemVer version directory from its manifest. Files: `version.py`,
  `manifest.py`, `vlnv.py`, `resolver.py`, `lockfile.py`, `__init__.py`,
  `tests/unit/test_version.py`, `test_resolver.py`, `test_manifest.py`,
  `test_vlnv.py`, `test_lockfile.py`. (Remaining versioning work is now only the
  *physical* multi-version coexistence at `gen` — name-mangling.)

### Versioning contract for the 1.0 freeze: conflict policies, multi-version, opaque scheme — June 2026
- [x] **Settled the resolver contract that was gating the 1.0 format freeze** —
  multi-version coexistence (bookkeeping), unification semantics, and the non-SemVer
  scheme floor, the three Open Non-Blocking versioning issues. The resolver now
  **always unifies SemVer-compatible dependents** (same major -> newest satisfying,
  Cargo-style; a diamond on `^1.0` + `^1.1` still collapses to one `1.1.x`) and gives
  the user a **conflict policy** for a genuinely *incompatible* conflict (two majors,
  or two distinct exact pins of an `opaque` core), set by a root `ip.toml`
  `[resolution] on-conflict` key with a `--on-conflict` CLI override:
  - `fail_on_conflict` (default) — raise `ResolutionError` (preserves prior behaviour;
    the demo's `soc_conflict/` still fails by default).
  - `use_latest` — collapse to the newest of the conflicting versions, prune orphans,
    and warn that lower requirements may be violated.
  - `isolate_namespaces` — keep every incompatible version in the resolve/lock/tree
    (multi-version **bookkeeping**, part (a) of the coexistence issue). Physical
    coexistence (name-mangling, part (b)) is not built, so `gen` **refuses** to emit
    two versions of one package with a clear message (`backends/edam.py`).
- [x] **Opt-in `[package].scheme` version scheme** (`semver` default, or `opaque`) and
  **explicit non-SemVer rejection**. A non-SemVer `package.version` is rejected under
  the default semver scheme at parse time with a clear `ManifestError` naming the
  string (the gating minimum (1) of the non-SemVer issue). `scheme = "opaque"` treats
  versions as opaque tokens: dependents must pin an exact `=` version and every distinct
  pin is its own compatibility group (honor-exact-pins), so the resolver never assumes
  compatibility it cannot verify.
- [x] **Genuinely non-SemVer version strings under `opaque`** — a new `OpaqueVersion`
  token (e.g. a vendor part number `D5020100`, calver `2024.1`, `r3`) is threaded
  through `Vlnv` (a scheme-aware `Vlnv.parse`), the manifest, `VersionConstraint`
  (exact-pin opaque constraints like `=D5020100`, with `^`/ranges refused), the
  lockfile (round-trips via a `scheme = "opaque"` marker per package), the tree, and
  the registry (`LocalRegistry.versions` reads the manifest for a non-SemVer version
  directory) -- and `pull`/`yank`, which take a VLNV string with no scheme, parse it
  as SemVer first and fall back to an opaque token (`cli._user_vlnv`), so pulling an
  opaque core by VLNV works. Verified against the consumer demo's new `soc_opaque/`
  (vendor IP at `D502../D401../DB..` part numbers, resolved by exact pin, `gen`-built,
  published + pulled). (The ordered non-SemVer schemes — calver/monotonic — landed
  next; see the milestone above.)
- [x] **Implementation**: a pure `compatibility_group(version, scheme)` and
  `VersionConstraint.is_exact`/`exact_version` in `version.py`; a grouped,
  scheme-aware backtracking solver keyed per `(package, compatibility-group)` node
  with a post-search policy fold and a reachability pass that prunes `use_latest`
  orphans (`resolver.py`); `Resolution` now exposes `vlnvs`/`by_ref`/`warnings` and
  may carry more than one version per package; `treeview.py` picks the per-edge
  version and expands per VLNV; the CLI threads the policy through
  resolve/install/tree/gen and prints warnings to stderr. Verified end to end against
  the external consumer demo's `soc_conflict/` (default fails; `isolate` resolves two
  `bus_pkg`; `gen` refuses; `use_latest` collapses to `2.0.0`), `soc/` (diamond still
  unifies to one `bus_pkg 1.1.0`), and `soc_opaque/` (opaque vendor part numbers).
  Files: `version.py`, `manifest.py`, `resolver.py`, `treeview.py`, `vlnv.py`,
  `lockfile.py`, `registry.py`, `backends/edam.py`, `cli.py`, `__init__.py`,
  `tests/unit/test_version.py`, `test_resolver.py`, `test_treeview.py`,
  `test_manifest.py`, `test_vlnv.py`, `test_lockfile.py`, `test_edam.py`,
  `tests/integration/test_conflict_policy_cli.py`.

### Hard gate: all PR checks must be green before merge — June 2026
- [x] **Green CI is now an explicit, hard gate before any merge.** A real incident
  drove this: PR #8 was merged while the `Test (py3.12, windows-latest)` check was
  red — a transient `actions/setup-python` flake (the `Install`/`Test` steps were
  *skipped*, not failed; `main`'s own push CI was green, so the code was fine). Two
  process bugs allowed it: the merge step watched a **single** workflow run instead of
  **all** PR checks, and piped `gh run watch` to `tail`, which **hid the non-zero exit
  code** so `gh pr merge --admin` ran anyway (and `--admin` bypasses required checks).
  Fix: the merge gate is now `gh pr checks <branch> --watch` (exit 0 over the whole
  matrix, never piped to a pager), `--admin` is documented as covering **only** the
  self-approval requirement (never a red/pending check), and a flaky run is re-run to
  green (`gh run rerun <id> --failed`) rather than bypassed. Updated
  `.claude/commands/release.md`, `CLAUDE.md`, `docs/ai_agent_instructions.md`.

### Branch model + agent-driven release flow + GitHub Release on tag — June 2026
- [x] **Adopted a `develop` (working) + `main` (release line) branch model; PRs are
  release-only.** Day-to-day work now commits directly to `develop` with **no PR**
  (`/tackle-issue` step 7 just makes the gates green and commits). `main` is the
  protected release line, updated **only** through the release flow: a `release/X.Y.Z`
  PR cut off `develop`, which — once CI is green — the agent **reviews with
  `/code-review`** (fixing in-scope findings, filing out-of-scope ones in Open
  Non-Blocking Issues) and **merges** with a merge commit (`gh pr merge --merge
  --admin`; GitHub forbids self-approval, so `--admin` satisfies the ruleset and logs
  the bypass), then tags `main` and fast-forwards `develop`. A **human gate applies
  only when the agent cannot safely decide on its own** — the `1.0.0` sign-off, a
  security-sensitive or hard-to-reverse change, or anything the user reserved.
  Mirrors the reference project's `develop`/`master` split. Updated `CLAUDE.md`,
  `docs/ai_agent_instructions.md`, `README.md`, `.claude/commands/release.md`, and
  `.claude/commands/tackle-issue.md`.
- [x] **`release.yml` creates a GitHub Release for each tag.** A new `github-release`
  job (gated on `needs: publish`, so it only announces what reached PyPI) builds the
  body from the tag's `docs/progress_tracker.md` entry plus a link to the PyPI page
  and attaches the wheel + sdist. The body logic is a pure, unit-tested helper
  (`scripts/extract_release_notes.py`: `extract_section` / `build_release_body`,
  falling back to a one-line summary when the tracker has no entry, e.g. a
  pre-release). Pre-release tags (`X.Y.Z-rc.N`) are marked `--prerelease`. Files:
  `.github/workflows/release.yml`, `scripts/extract_release_notes.py`,
  `tests/unit/test_extract_release_notes.py`, `docs/INDEX.md`.

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
