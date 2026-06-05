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

**Stage**: Foundation. The pure core is implemented, fully typed, linted, and
unit-tested (108 passing tests, ~96% coverage):
- **Versioning** — SemVer 2.0.0 `Version` + `VersionConstraint` (caret/tilde/range
  grammar, pre-release precedence).
- **Identity** — `PackageRef` and `Vlnv` (`vendor:library:name:version`).
- **Manifest** — `ip.toml` parsing/validation (`[package]`, `[dependencies]`,
  `[filesets]`, `[targets]`).
- **CLI** — `hdlpkg info`, `hdlpkg validate`, and `hdlpkg init` (scaffold a starter
  `ip.toml`) work; all other commands are wired and report planned status.
- **Tooling** — pytest (markers + coverage gate + foldable summary), ruff, mypy
  strict on `src/`, CI workflow, and a cross-platform test-summary renderer.

**Next**: implement the **Resolver** (see Roadmap M1).

---

## Roadmap (ordered — build top-down)

> Each milestone should land with tests and a docs update. The design for every
> item is in [architecture.md](./architecture.md); the rationale is in
> [research/state_of_the_art.md](./research/state_of_the_art.md).

| # | Milestone | Scope | Key files |
|---|-----------|-------|-----------|
| M1 | **Dependency resolver** | Constraints → one `Vlnv` per package; newest-compatible; fail-on-conflict; backtracking now, SAT-ready later. | `resolver.py` |
| M2 | **Lockfile (`ip.lock`)** | Serialize/verify a `Resolution` with per-core SHA-256 + source; read-back determinism. | `lockfile.py` (new) |
| M3 | **Content-addressed cache** | Local store keyed by digest; verify-on-read; offline reuse. | `registry.py`/`cache.py` |
| M4 | **Registry backends** | `Registry` impls: local dir, Git channel, HTTP index, **OCI artifact** registry. | `registry.py` |
| M5 | **`pack` / `publish` / `pull`** | Build `.ipkg`; append-only publish with yank; fetch by VLNV. | `cli.py`, `packaging.py` (new) |
| M6 | **Tool-flow generation** | EDAM-like intermediate → simulator/synth inputs (start: Verilator, Vivado). | `backends/` (new) |
| M7 | **IP-XACT export** | IEEE 1685 XML for Vivado/other-tool interop. | `ipxact.py` (new) |
| M8 | **Supply-chain** | Sigstore (cosign) signing + SBOM at `pack` time. | `packaging.py` |

---

## Blocking Issues (must fix before the next release)

_None._

---

## Open Non-Blocking Issues

| Issue | File | Notes |
|-------|------|-------|
| `hdlpkg tree` dependency view | `cli.py` | Pretty-print the dependency graph once the resolver (M1) exists. |
| Release automation (tag -> PyPI) | `.github/workflows/` | On an `X.Y.Z` tag: build wheel + sdist and publish to PyPI via OIDC trusted publishing (mirrors the reference project's tag-driven release). |

---

## Backlog (deferred — low value / not currently planned)

| Issue | Why parked |
|-------|------------|
| Switch build backend setuptools→`uv`/`hatch` workflow tooling | `hatchling` backend already works and is PEP-compliant; revisit only if the team standardizes on `uv` end to end. |
| Source-unit tokenizing (auto-discover HDL deps like Orbit) | Powerful but large; only worth it after the manifest-driven flow (M1–M5) is solid. |
| Dependabot / Renovate for dependency updates | Low effort, but mostly noise until the dev toolchain stabilizes; enable once the project is more active. |
| Mutation testing (`mutmut`) | Validates test quality, but slow and only worth it once the implemented surface is larger. |

---

## Completed Milestones

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
