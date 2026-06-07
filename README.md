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
hdlpkg pack ip.toml --sbom --search ../cores # also emit a CycloneDX SBOM
hdlpkg publish ip.toml --registry ../reg    # publish into a local registry
hdlpkg pull acme:common:fifo:1.0.0 --registry ../reg --output ./fifo
hdlpkg gen sim ip.toml --search ../cores     # generate Verilator/Vivado inputs for a target
hdlpkg tree ip.toml --search ../cores        # print the resolved dependency graph
hdlpkg export-ipxact ip.toml                 # export an IP-XACT (IEEE 1685) component XML
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
| [User guide](./docs/user_guide.md) | **Start here if you are new** — what the tool does and a hands-on walkthrough |
| [Module manual](./docs/modules/README.md) | Per-module reference + the full `hdlpkg` command reference |
| [AI agent instructions](./docs/ai_agent_instructions.md) | **Start here if you are an AI agent or new contributor** — briefing, file map, rules |
| [Architecture](./docs/architecture.md) | Module map, manifest/lockfile design, data flow, roadmap |
| [State of the art](./docs/research/state_of_the_art.md) | Research survey of package managers (pip/npm/cargo/docker) and HDL tools (FuseSoC, IP-XACT, Orbit, Bender) |
| [Progress tracker](./docs/progress_tracker.md) | What is done, in progress, and planned |
| [Quick-find index](./docs/INDEX.md) | Every file, concept, and topic |

---

## Development workflow

`main` is governed by the repository ruleset named **"main"**: **no direct commits
to `main`**, no force-pushes, and no branch deletion. Every change lands through a
pull request.

1. **Branch off `main`** — `git checkout -b feature/<thing>` (use `fix/`, `docs/`,
   or `release/X.Y.Z` prefixes as appropriate).
2. **Implement with tests.** Keep docs in sync as you go — run the `/update-docs`
   checklist (`docs/progress_tracker.md`, `docs/architecture.md`, `docs/INDEX.md`,
   and this README if user-visible behaviour changed).
3. **Make the gates green** before pushing: `pytest`, `ruff check .`,
   `ruff format --check .`, `mypy`. The pre-commit hooks (`pre-commit install`) run
   ruff + mypy on each commit so these are caught locally before CI.
4. **Push the branch and open a PR into `main`.** CI runs on the PR and Copilot
   reviews it automatically.
5. **Get one approving review, then merge with a merge commit.** Squash and rebase
   merges are disabled by the ruleset (`allowed_merge_methods: ["merge"]`). Because
   last-push approval is required, any commit pushed after an approval needs a fresh
   approval before the merge.

The PR approval and merge are a human gate; agents prepare the branch and PR and
stop there. (The ruleset's enforcement can be toggled in repo settings, but the
workflow above is the project's contract regardless.)

### Releasing

Releases are **tag-driven**, and the `X.Y.Z` tag must sit on the merge commit on
`main` — so a release goes through the same PR flow, not a direct push:

1. On a `release/X.Y.Z` branch, bump the version in **both** `pyproject.toml` and
   `src/hdl_ip_packager/__init__.py`, record the release in
   `docs/progress_tracker.md`, and make the gates green.
2. Open a PR into `main`, get it approved, and **merge with a merge commit**.
3. On the updated `main`, create and push the bare `X.Y.Z` tag (no `v` prefix).
   `.github/workflows/release.yml` then builds the wheel + sdist and publishes to
   PyPI via OIDC trusted publishing; a guard (`scripts/check_release_version.py`)
   fails the run if the tag and the packaged version disagree, so the tag is the
   single source of truth for the published version.

(One-time: register the repo as a PyPI trusted publisher and create the `pypi`
environment.) The `/release` agent command in `.claude/commands/` automates the
mechanics (bump both version files, run the gates, prepare the release PR, then —
after the human-approved merge — tag `main` and watch Actions + PyPI to green).

See [docs/ai_agent_instructions.md](./docs/ai_agent_instructions.md) for the full
agent obligations and coding conventions.

## License

[MIT](./LICENSE) © 2026 German Bravo Lopez.
