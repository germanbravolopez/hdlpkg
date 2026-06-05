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
- **CLI** — `hdlpkg info` and `hdlpkg validate` work; all other commands are wired
  and report planned status.
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
| `hdlpkg init` scaffolder | `cli.py` | Generate a starter `ip.toml` from prompts/flags. Small, high-value DX win; can land before M1. |
| `hdlpkg tree` dependency view | `cli.py` | Pretty-print the dependency graph once the resolver (M1) exists. |
| Coverage gate ratchet | `pyproject.toml` | Raise `fail_under` from 85 toward ~95 as the implemented surface grows; it sits at ~96% today. |
| Pre-commit hooks (ruff + mypy) | `.pre-commit-config.yaml` | Run `ruff check` / `ruff format` / `mypy` on commit so issues are caught before CI. High value, low effort. |
| Property-based tests (Hypothesis) | `tests/unit/`, dev extra | Excellent fit for `version.py`: invariants like `Version.parse(str(v)) == v` and "sorted order matches SemVer precedence", plus fuzzing the constraint grammar. |
| Release automation (tag -> PyPI) | `.github/workflows/` | On an `X.Y.Z` tag: build wheel + sdist and publish to PyPI via OIDC trusted publishing (mirrors the reference project's tag-driven release). |
| Docs site (MkDocs Material -> GitHub Pages) | `mkdocs.yml`, `.github/workflows/` | Auto-build and publish `docs/` to GitHub Pages on push to `main`. |

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

### Examples and developer experience — June 2026
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
