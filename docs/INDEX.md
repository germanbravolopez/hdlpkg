# Index — HDL IP Packager

**Use Ctrl+F to find any topic, file, concept, or function.** Project-wide
quick-find reference.

---

## Documentation files

| File | What's in it |
|------|-------------|
| `docs/user_guide.md` | **New users start here** — what the tool does + a hands-on walkthrough |
| `docs/modules/` | The user manual: one reference page per module + the CLI (`modules/README.md` indexes it) |
| `docs/ai_agent_instructions.md` | **Agents start here** — briefing, file map, coding + testability rules, obligations |
| `docs/architecture.md` | Module map, data model, subsystem designs, data flow |
| `docs/progress_tracker.md` | Status, ordered roadmap, open issues, milestones |
| `docs/research/state_of_the_art.md` | Survey of package managers + HDL tools; design rationale + sources |
| `docs/INDEX.md` | This file |
| `docs/README.md` | docs/ folder navigation |
| `README.md` | Project overview, install, usage, workflow (repo root) |
| `tests/README.md` | Test suite layout and how to extend it |
| `CLAUDE.md` | Claude Code agent entry point (repo root) |

## Source files

| Module | File | Status |
|--------|------|--------|
| Versioning (SemVer + constraints) | `src/hdl_ip_packager/version.py` | implemented |
| Identity (VLNV) | `src/hdl_ip_packager/vlnv.py` | implemented |
| Manifest (`ip.toml`) | `src/hdl_ip_packager/manifest.py` | implemented |
| Scaffolder (`init`) | `src/hdl_ip_packager/scaffold.py` | implemented |
| Exceptions | `src/hdl_ip_packager/exceptions.py` | implemented |
| CLI (`hdlpkg`) | `src/hdl_ip_packager/cli.py` | implemented |
| Public API | `src/hdl_ip_packager/__init__.py` | implemented |
| `python -m` shim | `src/hdl_ip_packager/__main__.py` | implemented |
| Resolver | `src/hdl_ip_packager/resolver.py` | implemented |
| Lockfile (`ip.lock`) | `src/hdl_ip_packager/lockfile.py` | implemented |
| Content-addressed cache | `src/hdl_ip_packager/cache.py` | implemented |
| Registry (local + HTTP + OCI, all writable) | `src/hdl_ip_packager/registry.py` | implemented |
| Registry credentials (`login`/`logout`) | `src/hdl_ip_packager/credentials.py` | implemented |
| Packaging (`.ipkg`) | `src/hdl_ip_packager/packaging.py` | implemented |
| Tool-flow backends (`gen`) | `src/hdl_ip_packager/backends/` | implemented (Verilator, Vivado, Icarus, GHDL, Yosys) |
| Name-mangling (SV + VHDL packages) | `src/hdl_ip_packager/mangle.py` | implemented |
| Dependency tree view (`tree`) | `src/hdl_ip_packager/treeview.py` | implemented |
| IP-XACT export (`export-ipxact`) | `src/hdl_ip_packager/ipxact.py` | implemented (1685-2014) |
| SBOM (`pack --sbom`) | `src/hdl_ip_packager/sbom.py` | implemented (CycloneDX 1.5) |

## Tooling & build files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata, deps, and all tool config (pytest, coverage, ruff, mypy) — single source of truth |
| `scripts/render_test_summary.py` | Renders a foldable Markdown test report from JUnit XML into the GitHub step summary (and stdout locally) |
| `scripts/check_release_version.py` | Release guard: fails if a git tag does not match `[project].version` in `pyproject.toml` |
| `scripts/extract_release_notes.py` | Builds the GitHub Release body from the tag's `docs/progress_tracker.md` entry + a PyPI link |
| `scripts/gen_manpage.py` | Generates `man/hdlpkg.1` from the live CLI parser (command reference) + curated prose; `--check` gates that the committed page is current |
| `man/hdlpkg.1` | The generated `hdlpkg(1)` man page; `man/README.md` covers viewing and installing it |
| `.github/workflows/ci.yml` | CI: pytest + coverage + ruff + mypy across Python 3.11/3.12, renders the test summary |
| `.github/workflows/release.yml` | Tag-driven release: build wheel + sdist, publish to PyPI (OIDC), and create the GitHub Release |
| `.pre-commit-config.yaml` | Local git hooks mirroring CI (ruff lint + format, mypy on `src/`) + hygiene hooks |
| `mkdocs.yml` | MkDocs Material config for the docs site (nav over `docs/`, theme, validation) |
| `.github/workflows/docs.yml` | Builds the MkDocs site and publishes it to GitHub Pages on push to `main` |
| `.github/dependabot.yml` | Weekly grouped dependency-update PRs for pip + GitHub Actions |
| `.gitignore` / `.gitattributes` | Ignore rules (incl. `.hdlpkg/` cache) + line-ending normalization |
| `.claude/commands/` | Slash-command skills (`/coding-guidelines`, `/update-docs`, `/tackle-issue`, `/release`) |
| `examples/` | Bundled example IP cores (`fifo`, `uart`) with real `ip.toml` manifests + HDL |

## Tests

| File | Covers |
|------|--------|
| `tests/conftest.py` | Shared fixtures (`sample_manifest_toml`, `write_manifest`) + local per-module summary hook |
| `tests/unit/test_version.py` | SemVer parsing/precedence, constraint grammar, pre-release rules |
| `tests/unit/test_version_properties.py` | Hypothesis property tests: round-trip, total order, constraint containment, grammar fuzzing |
| `tests/unit/test_vlnv.py` | `PackageRef` / `Vlnv` parse, validate, round-trip |
| `tests/unit/test_manifest.py` | `ip.toml` happy paths + every validation error |
| `tests/unit/test_scaffold.py` | `init` scaffolder: rendered manifest round-trips, validation errors |
| `tests/unit/test_cli.py` | CLI commands, exit codes, output |
| `tests/unit/test_resolver.py` | Dependency resolver: newest-compatible, transitive, diamond, conflict, pre-release, backtracking, conflict policies, opaque scheme |
| `tests/unit/test_lockfile.py` | Lockfile model: round-trip, determinism, parse errors, checksum verification |
| `tests/integration/test_resolve_cli.py` | `hdlpkg resolve` end to end on the bundled examples |
| `tests/integration/test_conflict_policy_cli.py` | `on-conflict` policies end to end: fail / isolate / use_latest + `gen` refusing module coexistence |
| `tests/unit/test_mangle.py` | SV + VHDL package mangler: rewrite (comment/string-safe), declared-name scan, planner + refusals |
| `tests/integration/test_mangle_vhdl_gen_cli.py` | `gen` (ghdl) name-mangles coexisting VHDL packages end to end |
| `tests/integration/test_mangle_gen_cli.py` | `gen` name-mangles coexisting packages end to end (per-consumer routing) |
| `tests/integration/test_opaque_registry_cli.py` | Opaque (non-SemVer) version published + resolved from a registry, lockfile scheme round-trip |
| `tests/integration/test_cache.py` | Content-addressed cache: round-trip, dedup, verify-on-read corruption |
| `tests/integration/test_registry.py` | Local + HTTP registries, graph walker, `install` fetch-into-cache |
| `tests/integration/test_http_registry_cli.py` | Writable + authenticated HTTP registry, full CLI publish/resolve/install/pull |
| `tests/integration/test_oci_registry_cli.py` | OCI distribution v2 backend vs a mock registry, full CLI flow |
| `tests/integration/test_oci_auth_cli.py` | OCI token-exchange (401 challenge -> Basic realm -> access token) via the CLI |
| `tests/unit/test_credentials.py` | `Credential`/`CredentialStore` keying, TOML + legacy read, docker-config parsing |
| `tests/unit/test_registry_location.py` | `registry_from_location` dispatch + credential wiring + `parse_bearer_challenge` |
| `tests/unit/test_login_cli.py` | `hdlpkg login`/`logout` token storage + error paths |
| `tests/integration/test_packaging.py` | `.ipkg` pack determinism, round-trip, path-traversal guard |
| `tests/integration/test_pack_cli.py` | `pack`/`publish`/`pull`/`yank` CLI loop against a local registry |
| `tests/unit/test_edam.py` | `build_eda_design`: fileset selection, topo order, dedup, target errors |
| `tests/unit/test_backends.py` | Verilator `.vc` / Vivado `.tcl` rendering + `get_backend` registry |
| `tests/integration/test_gen_cli.py` | `hdlpkg gen` over the examples (resolve → assemble → render → write) |
| `tests/unit/test_treeview.py` | `render_dependency_tree`: ordering, version annotation, diamond `(*)` marking |
| `tests/integration/test_tree_cli.py` | `hdlpkg tree` over the examples |
| `tests/unit/test_ipxact.py` | `to_ipxact`: VLNV, fileSets/fileType, model views, determinism |
| `tests/integration/test_ipxact_cli.py` | `hdlpkg export-ipxact` writes a parseable component XML |
| `tests/unit/test_sbom.py` | `build_cyclonedx`: components, dependency edges, determinism |
| `tests/integration/test_sbom_cli.py` | `hdlpkg pack --sbom` writes a CycloneDX SBOM with resolved deps |
| `tests/unit/test_docs_site.py` | `mkdocs.yml` parses and every `nav` page exists under `docs/` |
| `tests/unit/test_precommit_config.py` | `.pre-commit-config.yaml` parses and keeps the CI-mirroring hooks |
| `tests/unit/test_check_release_version.py` | Release version guard: tag-to-version parsing + tag/package match check |
| `tests/unit/test_extract_release_notes.py` | GitHub Release body: tracker-section extraction + PyPI-link composition |
| `tests/integration/test_manifest_cli_flow.py` | Manifest-on-disk → CLI end to end |
| `tests/integration/test_examples.py` | Bundled `examples/` cores validate, file paths exist, deps stay in-tree |

## CLI commands

| Command | Status | Purpose |
|---------|--------|---------|
| `hdlpkg info [path]` | implemented | Print parsed identity, deps, filesets, targets |
| `hdlpkg validate [path]` | implemented | Parse + validate a manifest (exit 0 if OK) |
| `hdlpkg init [dir]` | implemented | Scaffold a starter `ip.toml` (flags or interactive prompts) |
| `hdlpkg add <dep> [path] [--version]` | implemented | Add/update a dependency in `ip.toml` (text-preserving) |
| `hdlpkg resolve [path] [--search DIR] [--registry LOCATION] [--output] [--on-conflict]` | implemented | Resolve deps (source scan or a published `--registry`: dir / `http(s)://` / `oci://`), write `ip.lock`; `--on-conflict` overrides the policy |
| `hdlpkg install [path] [--search] [--registry LOCATION] [--cache-dir] [--locked] [--on-conflict]` | implemented | Resolve + fetch into the verified cache (source scan or a published `--registry`); `--locked` installs exactly from `ip.lock` |
| `hdlpkg pack [path] [--output] [--sbom] [--search]` | implemented | Build a deterministic `.ipkg`; `--sbom` also writes a CycloneDX SBOM |
| `hdlpkg publish [path] --registry LOCATION` | implemented | Publish a core to a registry (local dir / `http(s)://` / `oci://`), append-only |
| `hdlpkg pull <vlnv> --registry LOCATION [--output]` | implemented | Fetch a core by VLNV (SemVer or opaque) into the cache; optionally extract |
| `hdlpkg yank <vlnv> --registry LOCATION` | implemented | Hide a published version (SemVer or opaque VLNV) from new resolves (local registry) |
| `hdlpkg login <location> [--username U] [--token/--password S]` | implemented | Store credentials for a private http(s)/oci registry; `--username` selects the OCI token-exchange (HTTP Basic), else a direct bearer token (prompts if the secret is omitted) |
| `hdlpkg logout <location>` | implemented | Remove a stored registry token |
| `hdlpkg gen <target> [--search DIR] [--output DIR] [--locked] [--on-conflict]` | implemented | Generate tool-flow inputs (Verilator/Vivado/Icarus/GHDL/Yosys); `--locked` pins deps from `ip.lock`; refuses two versions of one package |
| `hdlpkg tree [--search DIR] [--registry DIR]` | implemented | Print the resolved dependency graph as a tree |
| `hdlpkg export-ipxact [--output FILE]` | implemented | Export an IP-XACT (IEEE 1685-2014) component XML |

## Glossary

| Term | Definition |
|------|-----------|
| **VLNV** | `vendor:library:name:version` — IP-XACT core identity scheme |
| **PackageRef** | The version-less `vendor:library:name` triple (a dependency key) |
| **Manifest** | The per-core `ip.toml` declaring identity, deps, filesets, targets |
| **Lockfile** | `ip.lock` — generated exact-version + integrity record (one `[[package]]` per dep) |
| **`.ipkg`** | The deterministic, distributable package of a core (gzip+tar of manifest + fileset files) |
| **Registry location** | The `--registry` string dispatched by `registry_from_location`: a local dir / `http(s)://` / `oci://` |
| **OCI registry** | A registry speaking the OCI distribution v2 API (Harbor/Artifactory/Zot/...); cores stored as OCI artifacts. Private + self-hostable |
| **Credentials** | Per-host registry secrets (bearer token, or username+password), set by `hdlpkg login` (`~/.hdlpkg/credentials.toml`); `docker login` reused as a fallback |
| **OCI token-exchange** | The Docker/OCI auth dance: a `401` + `WWW-Authenticate: Bearer realm=...` challenge, then a Basic (or anonymous) call to the realm for a short-lived scoped access token |
| **Yank** | Hide a published version from new resolves without deleting it (old lockfiles still verify) |
| **Fileset** | A named group of HDL source files of one type |
| **Target** | A build config: which filesets feed which tool flow + the top unit |
| **Tool flow** | A back-end (Verilator, Vivado, …) the packager generates inputs for |
| **EDAM** | Intermediate tool-agnostic build description (FuseSoC concept) |
| **Resolution** | The `Vlnv`(s) chosen per package satisfying all constraints (`vlnvs`/`by_ref`/`warnings`) |
| **Content-addressed** | Stored/looked-up by SHA-256 digest (integrity + dedup) |
| **SemVer** | Semantic Versioning 2.0.0 — the default versioning contract |
| **Version scheme** | `[package].scheme`: `semver` (default) / `calver` (`2024.1`) / `monotonic` (`r3`) / `opaque` (uninterpreted token) |
| **CalVer** | Ordered numeric calendar version (`2024.1`); year-as-major (`^2024.1` = `>=2024.1, <2025`) — `CalVer` |
| **Monotonic version** | An ordered revision (`r3`, `12`); one shared compatibility group, `^r3` = `>=r3` — `MonotonicVersion` |
| **Opaque version** | A non-SemVer version token (`D5020100`) — exact-pinned, no ordering (`OpaqueVersion`) |
| **Compatibility group** | The set a version belongs to for unification (SemVer major / CalVer year / one monotonic group / opaque token) |
| **Conflict policy** | `[resolution] on-conflict`: `fail_on_conflict` / `use_latest` / `isolate_namespaces` |
| **Name-mangling** | Renaming a coexisting package (SystemVerilog or VHDL) per version (`bus_pkg` -> `bus_pkg__v1_1_0`) so two versions build together (`mangle.py`) |
| **IP-XACT** | IEEE 1685 XML standard for packaging/describing IP |

## Topics → where to look

| Topic | Where |
|-------|-------|
| Getting started / what the tool does | `docs/user_guide.md` |
| How a specific module behaves (reference) | `docs/modules/<module>.md` (indexed by `docs/modules/README.md`) |
| Every CLI command + flag | `docs/modules/cli.md` |
| Why these design choices | `docs/research/state_of_the_art.md` |
| How a manifest is parsed | `src/hdl_ip_packager/manifest.py` + `docs/architecture.md` §3 |
| Constraint syntax (`^`, `~`, ranges) | `src/hdl_ip_packager/version.py` + `docs/architecture.md` §3 |
| Pre-release matching rule | `src/hdl_ip_packager/version.py` (`VersionConstraint`) |
| Conflict policy / multi-version coexistence | `docs/modules/resolver.md` + `src/hdl_ip_packager/resolver.py` |
| Name-mangling (SV + VHDL package coexistence at `gen`) | `docs/modules/mangle.md` + `src/hdl_ip_packager/mangle.py` |
| Non-SemVer version schemes (calver / monotonic / opaque) | `docs/modules/versioning.md` (`CalVer` / `MonotonicVersion` / `OpaqueVersion`) + `src/hdl_ip_packager/version.py` |
| Adding a new CLI command | `src/hdl_ip_packager/cli.py` (`build_parser`) |
| Adding a new module | `docs/ai_agent_instructions.md` + `docs/README.md` |
| Test layout / adding tests | `tests/README.md` |
| Test summary in CI | `scripts/render_test_summary.py` + `.github/workflows/ci.yml` |
| Roadmap / what to build next | `docs/progress_tracker.md` |
| Coding conventions | `docs/ai_agent_instructions.md` + `.claude/commands/coding-guidelines.md` |
| Branch & merge workflow (PR → merge commit) | `docs/ai_agent_instructions.md` + `README.md` §Development workflow (ruleset "main") |
| Cutting a release | `README.md` §Releasing + `.claude/commands/release.md` |
