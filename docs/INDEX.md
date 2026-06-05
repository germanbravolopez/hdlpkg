# Index — HDL IP Packager

**Use Ctrl+F to find any topic, file, concept, or function.** Project-wide
quick-find reference.

---

## Documentation files

| File | What's in it |
|------|-------------|
| `docs/ai_agent_instructions.md` | **Start here** — briefing, file map, coding + testability rules, obligations |
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
| Exceptions | `src/hdl_ip_packager/exceptions.py` | implemented |
| CLI (`hdlpkg`) | `src/hdl_ip_packager/cli.py` | implemented |
| Public API | `src/hdl_ip_packager/__init__.py` | implemented |
| `python -m` shim | `src/hdl_ip_packager/__main__.py` | implemented |
| Resolver | `src/hdl_ip_packager/resolver.py` | planned (seam) |
| Registry / cache | `src/hdl_ip_packager/registry.py` | planned (seam) |

## Tooling & build files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata, deps, and all tool config (pytest, coverage, ruff, mypy) — single source of truth |
| `scripts/render_test_summary.py` | Renders a foldable Markdown test report from JUnit XML into the GitHub step summary (and stdout locally) |
| `.github/workflows/ci.yml` | CI: pytest + coverage + ruff + mypy across Python 3.11/3.12, renders the test summary |
| `.gitignore` / `.gitattributes` | Ignore rules (incl. `.hdlpkg/` cache) + line-ending normalization |
| `.claude/commands/` | Slash-command skills (`/coding-guidelines`, `/update-docs`) |

## Tests

| File | Covers |
|------|--------|
| `tests/conftest.py` | Shared fixtures (`sample_manifest_toml`, `write_manifest`) + local per-module summary hook |
| `tests/unit/test_version.py` | SemVer parsing/precedence, constraint grammar, pre-release rules |
| `tests/unit/test_vlnv.py` | `PackageRef` / `Vlnv` parse, validate, round-trip |
| `tests/unit/test_manifest.py` | `ip.toml` happy paths + every validation error |
| `tests/unit/test_cli.py` | CLI commands, exit codes, output |
| `tests/unit/test_planned_stubs.py` | Resolver/registry seams import and fail loudly |
| `tests/integration/test_manifest_cli_flow.py` | Manifest-on-disk → CLI end to end |

## CLI commands

| Command | Status | Purpose |
|---------|--------|---------|
| `hdlpkg info [path]` | implemented | Print parsed identity, deps, filesets, targets |
| `hdlpkg validate [path]` | implemented | Parse + validate a manifest (exit 0 if OK) |
| `hdlpkg init` | planned | Scaffold a starter `ip.toml` |
| `hdlpkg add <vlnv>` | planned | Add a dependency to `ip.toml` |
| `hdlpkg resolve` | planned | Resolve deps, write `ip.lock` |
| `hdlpkg install` | planned | Resolve + fetch into the cache |
| `hdlpkg pack` | planned | Build a `.ipkg` artifact |
| `hdlpkg publish` | planned | Publish to a registry |
| `hdlpkg pull <vlnv>` | planned | Download a core by VLNV |
| `hdlpkg gen <target>` | planned | Generate tool/back-end files (EDAM) |
| `hdlpkg export-ipxact` | planned | Export IP-XACT (IEEE 1685) for tool interop |

## Glossary

| Term | Definition |
|------|-----------|
| **VLNV** | `vendor:library:name:version` — IP-XACT core identity scheme |
| **PackageRef** | The version-less `vendor:library:name` triple (a dependency key) |
| **Manifest** | The per-core `ip.toml` declaring identity, deps, filesets, targets |
| **Lockfile** | `ip.lock` — generated exact-version + integrity record (planned) |
| **Fileset** | A named group of HDL source files of one type |
| **Target** | A build config: which filesets feed which tool flow + the top unit |
| **Tool flow** | A back-end (Verilator, Vivado, …) the packager generates inputs for |
| **EDAM** | Intermediate tool-agnostic build description (FuseSoC concept) |
| **Resolution** | One concrete `Vlnv` chosen per package satisfying all constraints |
| **Content-addressed** | Stored/looked-up by SHA-256 digest (integrity + dedup) |
| **Yank** | Retire a published version without breaking existing lockfiles |
| **SemVer** | Semantic Versioning 2.0.0 — the versioning contract |
| **IP-XACT** | IEEE 1685 XML standard for packaging/describing IP |

## Topics → where to look

| Topic | Where |
|-------|-------|
| Why these design choices | `docs/research/state_of_the_art.md` |
| How a manifest is parsed | `src/hdl_ip_packager/manifest.py` + `docs/architecture.md` §3 |
| Constraint syntax (`^`, `~`, ranges) | `src/hdl_ip_packager/version.py` + `docs/architecture.md` §3 |
| Pre-release matching rule | `src/hdl_ip_packager/version.py` (`VersionConstraint`) |
| Adding a new CLI command | `src/hdl_ip_packager/cli.py` (`build_parser`) |
| Adding a new module | `docs/ai_agent_instructions.md` + `docs/README.md` |
| Test layout / adding tests | `tests/README.md` |
| Test summary in CI | `scripts/render_test_summary.py` + `.github/workflows/ci.yml` |
| Roadmap / what to build next | `docs/progress_tracker.md` |
| Coding conventions | `docs/ai_agent_instructions.md` + `.claude/commands/coding-guidelines.md` |
