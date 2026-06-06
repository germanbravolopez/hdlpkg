# HDL IP Packager

[![CI](https://github.com/germanbravolopez/hdl-ip-packager/actions/workflows/ci.yml/badge.svg)](https://github.com/germanbravolopez/hdl-ip-packager/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
![Status](https://img.shields.io/badge/status-pre--alpha-orange)

A package manager and dependency resolver for **HDL IP cores** — bringing the
ergonomics of `pip` / `npm` / `cargo` / `docker pull` to Verilog, VHDL, and
SystemVerilog design reuse. Built in **Python 3.11+**.

> **Project status: pre-alpha / foundation.** The versioning, identity (VLNV),
> and manifest layers are implemented and tested; resolution, packaging, and
> registries are designed and stubbed. See
> [docs/progress_tracker.md](./docs/progress_tracker.md) for exactly what is done
> versus planned, and [docs/architecture.md](./docs/architecture.md) for the design.

---

## Why

Hardware teams re-use IP constantly, but sharing it is still mostly manual: copy
files, hand-track versions, hope the dependency you vendored matches the one your
colleague used. Software solved this with package managers. The mature HDL
attempts (FuseSoC, Bender, Orbit, IP-XACT/IEEE 1685, vendor catalogs) each got
part of the way. This project distills the state of the art into one tool — see
the research write-up in [docs/research/state_of_the_art.md](./docs/research/state_of_the_art.md).

## Features

Implemented today:

- **VLNV identity** — cores are named `vendor:library:name:version` (the IP-XACT
  convention), so names are globally meaningful and collision-resistant.
- **Semantic versioning** — full SemVer 2.0.0 parsing/precedence plus a
  constraint grammar (`^`, `~`, `>=`, `<`, ranges, `*`) for dependency specs.
- **Manifest (`ip.toml`)** — a TOML manifest per core declaring identity,
  metadata, filesets, dependencies, and build targets.
- **Dependency resolver** — backtracking, newest-compatible resolution to one
  `Vlnv` per package (fail-on-conflict, pre-release-aware).
- **Lockfile (`ip.lock`)** — a deterministic, verifiable record of a resolve
  (exact VLNVs + source + SHA-256), written by `hdlpkg resolve`.
- **Content-addressed cache + registries** — a SHA-256-keyed local cache with
  verify-on-read, fed by local-directory and HTTP registry backends; `hdlpkg
  install` resolves and fetches dependencies into it.
- **Packaging + distribution** — a deterministic `.ipkg` artifact with `pack`,
  append-only `publish` (with `yank`), and `pull` (fetch by VLNV into the cache).
- **CLI (`hdlpkg`)** — `info`, `validate`, `init`, `resolve`, `install`, `pack`,
  `publish`, `pull`, and `yank` work today; the rest is wired and reports planned
  status.

Designed and on the roadmap (see the progress tracker):

- Additional **registries** (Git-backed channel, OCI artifact registry).
- Tool-flow **generation** (EDAM) and **IP-XACT export** for Vivado/other-tool interop.

---

## Requirements

| Dependency | Version |
|------------|---------|
| Python | 3.11+ (uses stdlib `tomllib`) |
| OS | Windows, Linux, macOS (pure Python) |
| Runtime deps | none yet (kept minimal by design) |

## Install

```powershell
# From a clone, install in editable mode with the dev/test toolchain:
python -m pip install -e ".[dev]"
```

This puts the `hdlpkg` command on your PATH and installs pytest, ruff, mypy, and
pre-commit. Enable the local git hooks (ruff + mypy on commit) once with:

```powershell
pre-commit install
```

## Usage

```powershell
hdlpkg --help                 # show all commands
hdlpkg init --vendor acme --library comm --name uart   # scaffold a starter ip.toml
hdlpkg info ip.toml           # print the parsed identity, deps, filesets, targets
hdlpkg validate ip.toml       # parse + validate a manifest (exit 0 if OK)
hdlpkg resolve ip.toml --search ../cores   # resolve deps to a deterministic ip.lock
hdlpkg install ip.toml --search ../cores   # resolve + fetch deps into the cache
hdlpkg pack ip.toml                         # build a distributable .ipkg
hdlpkg publish ip.toml --registry ../reg    # publish into a local registry
hdlpkg pull acme:common:fifo:1.0.0 --registry ../reg --output ./fifo
python -m hdl_ip_packager info   # same CLI, invoked as a module
```

A minimal `ip.toml`:

```toml
[package]
vendor  = "acme"
library = "comm"
name    = "uart"
version = "1.2.0"

[dependencies]
"acme:common:fifo" = "^1.0.0"

[filesets.rtl]
files = ["rtl/uart_top.sv"]
type  = "systemVerilogSource"

[targets.sim]
toolflow = "verilator"
filesets = ["rtl"]
top      = "uart_top"
```

Two complete, working cores live under [`examples/`](examples/) — a FIFO
(`acme:common:fifo`) and a UART (`acme:comm:uart`) that depends on it:

```powershell
hdlpkg info examples/uart/ip.toml
hdlpkg validate examples/fifo/ip.toml
hdlpkg resolve examples/uart/ip.toml --search examples   # writes examples/uart/ip.lock
```

---

## Tests

The suite uses **pytest** with a scalable, marker-based layout and a foldable
summary report. From the repo root:

```powershell
pytest                                   # run everything (with the local summary)
pytest -m unit                           # only fast unit tests
pytest -m "not integration"              # skip filesystem/integration tests
pytest --cov=hdl_ip_packager --cov-report=term-missing   # with coverage

# Produce the JUnit XML + the rendered Markdown report (what CI shows):
pytest --junitxml=test-results.xml
python scripts/render_test_summary.py --title "Test results"
```

See [tests/README.md](./tests/README.md) for how the suite is organized and how
to add new test modules. CI runs the suite on every push/PR and renders the
summary into the GitHub Actions run page.

---

## Documentation

Full technical documentation lives in [`docs/`](./docs/README.md) and is published
as a site at <https://germanbravolopez.github.io/hdl-ip-packager/> (built from
`docs/` by [`.github/workflows/docs.yml`](./.github/workflows/docs.yml) on every
push to `main`). To preview it locally:

```powershell
pip install -e ".[docs]"
mkdocs serve
```

| Document | Description |
|----------|-------------|
| [AI agent instructions](./docs/ai_agent_instructions.md) | **Start here if you are an AI agent or new contributor** — briefing, file map, rules |
| [Architecture](./docs/architecture.md) | Module map, manifest/lockfile design, data flow, roadmap |
| [State of the art](./docs/research/state_of_the_art.md) | Research survey of package managers (pip/npm/cargo/docker) and HDL tools (FuseSoC, IP-XACT, Orbit, Bender) |
| [Progress tracker](./docs/progress_tracker.md) | What is done, in progress, and planned |
| [Quick-find index](./docs/INDEX.md) | Every file, concept, and topic |

---

## Development workflow

This project follows the same branch model as its sibling projects: **never
commit directly to `main`.** Work happens on a branch and merges via pull request.

1. Branch off `main` (e.g. `git checkout -b feature/resolver`).
2. Implement with tests. Keep docs in sync as you go — run the `/update-docs`
   checklist (`docs/progress_tracker.md`, `docs/architecture.md`, `docs/INDEX.md`,
   and this README if user-visible behaviour changed).
3. Before merging, the branch must be green: `pytest`, `ruff check .`, and
   `mypy` all pass. The pre-commit hooks (`pre-commit install`) run ruff + mypy on
   each commit so these are caught locally before CI.
4. Open a PR into `main` and merge with a merge commit.

### Releasing

Releases are tag-driven. Bump `[project].version` in `pyproject.toml`, then push a
matching `X.Y.Z` tag: `.github/workflows/release.yml` builds the wheel + sdist and
publishes them to PyPI via OIDC trusted publishing. A guard
(`scripts/check_release_version.py`) fails the run if the tag and the packaged
version disagree, so the tag is the single source of truth for the published
version. (One-time: register the repo as a PyPI trusted publisher and create the
`pypi` environment.) The `/release` agent command in `.claude/commands/` automates
this end to end (bump both version files, run the gates, record the release, tag,
push, then watch Actions + PyPI to green).

See [docs/ai_agent_instructions.md](./docs/ai_agent_instructions.md) for the full
agent obligations and coding conventions.

## License

[MIT](./LICENSE) © 2026 German Bravo Lopez.
