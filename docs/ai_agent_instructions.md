# AI Agent Instructions — HDL IP Packager

**Read this first. This file is your briefing.** Everything critical fits below;
references lead you to detail when needed. If you are a human contributor, this is
also the fastest onboarding path.

---

## Project in one paragraph

The **HDL IP Packager** is a Python 3.11+ tool that brings package-manager
ergonomics (think `pip`/`npm`/`cargo`/`docker pull`) to **HDL IP cores**
(Verilog/VHDL/SystemVerilog). Each core carries an `ip.toml` manifest declaring a
**VLNV** identity (`vendor:library:name:version`), metadata, source filesets,
dependencies (as SemVer constraints), and build targets. The library
(`hdlpkg`) and CLI (`hdlpkg`) provide the **manifest → resolve → lock →
fetch → generate** pipeline. The foundation (versioning, identity, manifest) is
implemented and tested; resolution, registries, packaging, and tool-flow
generation are designed and stubbed. Design rationale lives in
[research/state_of_the_art.md](./research/state_of_the_art.md).

## Status & what to work on next

No blocking issues. The project is at the **foundation** stage. The ordered
roadmap (Resolver → Lockfile → Cache/Registry → Pack/Publish → Generate →
IP-XACT export → Supply-chain) is in [progress_tracker.md](./progress_tracker.md).
**Always read the progress tracker before starting** — it is the single source of
truth for what is done versus planned.

## Build & run

- **Requirements**: Python 3.11+ (uses stdlib `tomllib`). No runtime deps yet.
- **Set up the dev environment** (editable install + test/lint/type tools):
  ```powershell
  python -m pip install -e ".[dev]"
  ```
- **Run the tool**: `hdlpkg --help`, or `python -m hdlpkg --help` (works
  even if the script dir is not on PATH).
- **Quality gates** (all must pass before merge):
  ```powershell
  pytest                       # tests + coverage gate (fail_under in pyproject)
  ruff check .                 # lint
  ruff format --check .        # formatting
  mypy                         # strict typing on src/
  ```
  Optionally `pre-commit install` to run ruff + mypy automatically on each commit
  (config in `.pre-commit-config.yaml`).

## Branch & merge workflow

**`main` is the trunk** and the only long-lived branch — protected (ruleset "main": no
direct commits/pushes, no force-push, no deletion, merge-commit-only), so **every
change reaches it through a PR**. Never commit on `main` directly.

1. Do the work on a **short-lived branch off an up-to-date `main`** (`git switch main &&
   git pull --ff-only && git switch -c feature/X`); make the quality gates green,
   commit, push, and open a PR into `main` (`gh pr create --base main`). CI runs on the
   PR. (A release is the same flow plus a version bump + tag — cut `release/X.Y.Z` off
   `main`; see `/release`.)
2. Once CI is green, **review the PR with `/code-review`** and resolve every finding —
   fix it, or, if it's out of scope, file it in `docs/progress_tracker.md` Open
   Non-Blocking Issues. Never merge with an open, unaddressed finding.
3. **Confirm every PR check is green (hard gate)** with `gh pr checks <branch> --watch`
   (must exit 0 — the whole CI matrix, not one workflow; never pipe to `tail`, which
   hides the exit code). A flaky infra failure is re-run to green
   (`gh run rerun <id> --failed`), never bypassed.
4. **Merge with a merge commit** — `gh pr merge --merge --admin --delete-branch` (squash
   and rebase are disabled, `allowed_merge_methods: ["merge"]`; GitHub forbids approving
   your own PR, so `--admin` covers **only** the required-review / last-push approval —
   never use it to merge past a red or pending check). For a release, then **tag the
   merged `main`** to publish (nothing to fast-forward — `main` is the only long-lived
   branch).

**Defer to a human gate only when the agent cannot safely decide on its own** — the
`1.0.0` stability sign-off, a security-sensitive or hard-to-reverse change, or
anything the user has explicitly reserved; there, prepare the branch + PR and stop.
The `/tackle-issue` and `/release` commands encode this flow (see
[README](https://github.com/germanbravolopez/hdlpkg/blob/main/README.md) -> Releasing).

## File map — where to find what

| What you need | Where |
|---------------|-------|
| CLI entry point | [src/hdlpkg/cli.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/cli.py) (`main`) |
| Public API exports | [src/hdlpkg/__init__.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/__init__.py) |
| SemVer + constraints | [src/hdlpkg/version.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/version.py) |
| VLNV identity | [src/hdlpkg/vlnv.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/vlnv.py) |
| `ip.toml` parsing/validation | [src/hdlpkg/manifest.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/manifest.py) |
| Exception hierarchy | [src/hdlpkg/exceptions.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/exceptions.py) |
| Resolver | [src/hdlpkg/resolver.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/resolver.py) |
| Lockfile (`ip.lock`) | [src/hdlpkg/lockfile.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/lockfile.py) |
| Content-addressed cache | [src/hdlpkg/cache.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/cache.py) |
| Registry (local/HTTP/writable) | [src/hdlpkg/registry.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/registry.py) |
| Packaging (`.ipkg`) | [src/hdlpkg/packaging.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/packaging.py) |
| Tool-flow backends (`gen`) | [src/hdlpkg/backends/](https://github.com/germanbravolopez/hdlpkg/tree/main/src/hdlpkg/backends) |
| IP-XACT / SBOM / tree view | [ipxact.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/ipxact.py), [sbom.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/sbom.py), [treeview.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/treeview.py) |
| Per-module reference (manual) | [docs/modules/](modules/README.md) |
| Tests | [tests/](https://github.com/germanbravolopez/hdlpkg/tree/main/tests) — see [tests/README.md](https://github.com/germanbravolopez/hdlpkg/blob/main/tests/README.md) |
| Test summary renderer | [scripts/render_test_summary.py](https://github.com/germanbravolopez/hdlpkg/blob/main/scripts/render_test_summary.py) |
| Project + tool config | [pyproject.toml](https://github.com/germanbravolopez/hdlpkg/blob/main/pyproject.toml) (single source of truth) |
| CI pipeline | [.github/workflows/ci.yml](https://github.com/germanbravolopez/hdlpkg/blob/main/.github/workflows/ci.yml) |

## Documentation map

| Document | Purpose |
|----------|---------|
| `README.md` | Project overview, install, usage, workflow (root) |
| `docs/ai_agent_instructions.md` | This briefing |
| `docs/architecture.md` | Module map, data model, subsystem designs, data flow |
| `docs/progress_tracker.md` | Done / in-progress / planned — read before working |
| `docs/research/state_of_the_art.md` | Research survey backing every design choice |
| `docs/INDEX.md` | Quick-find: every file, concept, topic |
| `docs/README.md` | docs/ folder navigation |
| `tests/README.md` | How the test suite is organized and how to extend it |

---

## Coding conventions (Python) — follow these for all new code

The implemented modules are the reference; match their style.

1. **Language & style**: Python 3.11+, **PEP 8** via `ruff format` (line length
   100). English for all identifiers, comments, docstrings, and log/error
   messages.
2. **Naming**: `snake_case` for functions/variables/modules, `PascalCase` for
   classes, `UPPER_SNAKE_CASE` for module constants, `_leading_underscore` for
   internal helpers. Boolean helpers read as `is_`/`has_`/`can_`.
3. **Types are mandatory** on every function signature in `src/`. `mypy --strict`
   must pass. Prefer precise types (`tuple[str, ...]`, `dict[str, object]`) over
   `Any`.
4. **Purity by default**: keep parsing/logic free of I/O and global state (see
   `version`/`vlnv`/`manifest`). Do filesystem/network only in the CLI and the
   registry layer. This is the single most important rule for testability.
5. **Immutable value types**: model data as `@dataclass(frozen=True)`. Parse with
   a `@classmethod` `parse`/`from_*`; render with `__str__`.
6. **Errors**: raise a subclass of `HdlPackagerError` (add one in `exceptions.py`
   if needed) with a message that names the offending input. Never `print` for
   errors in library code; never silently swallow.
7. **Docstrings**: a module docstring stating purpose + key design notes, and a
   one-line docstring on every public function/class stating its contract
   (what it returns, what counts as failure). Comment the *why*, not the *what*;
   keep inline comments to one or two lines.
8. **Dependencies**: keep runtime deps minimal — justify every new one in the PR
   and the progress tracker. Dev-only tools go in `[project.optional-dependencies].dev`.
9. **CLI**: keep it thin — parse args, delegate to library functions, return an
   exit code. No business logic in `cli.py`.

## Implement for testability — hard rule

- **Every new behaviour ships with tests in the same change.** No exceptions.
- **Write the logic as a pure function** you can call with plain values; if you
  find yourself needing the filesystem/network to test something, extract the
  pure decision into its own function and test that (this is exactly how
  `manifest` stays testable despite reading files).
- Put fast, isolated tests under `tests/unit/` (marker `unit`); multi-module or
  filesystem tests under `tests/integration/` (marker `integration`).
- Cover the **error paths**, not just the happy path — every `raise` should have a
  test.
- Keep coverage at or above the `fail_under` gate in `pyproject.toml`; raise the
  gate as the implemented surface grows. See [tests/README.md](https://github.com/germanbravolopez/hdlpkg/blob/main/tests/README.md).

## Agent obligations — after every change

1. **Update [progress_tracker.md](./progress_tracker.md)** — move the item, add a
   dated entry at the top of the relevant section. Never delete history; archive it.
2. **Update [architecture.md](./architecture.md)** when a module, the data model,
   or the data flow changed (flip a **(planned)** to **(implemented)**).
3. **Update [INDEX.md](./INDEX.md)** when files, concepts, or commands were added.
4. **Update `README.md`** when user-visible behaviour, install, or the CLI changed.
5. **Run the quality gates** (pytest + ruff + mypy) and make them green.
6. **No duplication** — if the same explanation exists in two docs, consolidate
   and link. Long-form goes in docs; code carries a one-line pointer.
7. **English only. No emojis in doc/heading text** (the test-report status icons
   in `scripts/` are the one intentional exception).
8. Consider the `/coding-guidelines` and `/update-docs` skills in
   [.claude/commands/](https://github.com/germanbravolopez/hdlpkg/tree/main/.claude/commands) — read the full skill file when relevant.

## Document size guidance

| File | Soft limit | When exceeded |
|------|-----------|---------------|
| `docs/ai_agent_instructions.md` | 150 lines | Move detail to `architecture.md` |
| `docs/architecture.md` | 400 lines | Split a subsystem into `docs/modules/<name>.md` |
| `docs/progress_tracker.md` | 250 lines | Move old milestones to Archive |
| `docs/INDEX.md` | 200 lines | Split by domain |
