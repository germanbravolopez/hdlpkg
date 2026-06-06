# HDL IP Packager — Claude Code Instructions

**Before starting any task**, read [docs/ai_agent_instructions.md](docs/ai_agent_instructions.md)
in full. It is the project briefing: status, file map, coding + testability rules,
and your obligations as an agent.

Quick links:
- [docs/ai_agent_instructions.md](docs/ai_agent_instructions.md) — start here
- [docs/progress_tracker.md](docs/progress_tracker.md) — status + the ordered roadmap (read before working)
- [docs/architecture.md](docs/architecture.md) — module map, data model, subsystem designs
- [docs/research/state_of_the_art.md](docs/research/state_of_the_art.md) — why the design is what it is
- [docs/INDEX.md](docs/INDEX.md) — find any file, concept, or topic
- [.claude/commands/](.claude/commands/) — slash commands (`/coding-guidelines`, `/update-docs`, `/tackle-issue`, `/release`)

## After completing any task

1. Make the quality gates green: `pytest`, `ruff check .`, `ruff format --check .`, `mypy`.
2. Run `/update-docs` (or follow its checklist) to keep the docs current — at
   minimum `docs/progress_tracker.md`, plus `architecture.md`/`INDEX.md`/`README.md`
   when relevant.

## Coding rules (summary — full version in the docs)

- **Python 3.11+**, PEP 8 via `ruff format` (line length 100). English everywhere.
- **Types mandatory** on `src/` (mypy `--strict`). Model data as
  `@dataclass(frozen=True)` with `parse`/`from_*` classmethods.
- **Purity by default**: keep logic free of I/O; do filesystem/network only in the
  CLI and registry layers. This is the testability rule — see
  [.claude/commands/coding-guidelines.md](.claude/commands/coding-guidelines.md).
- **Every behaviour ships with tests** in the same change, covering error paths.
- **Errors** derive from `HdlPackagerError`; never `print` errors in library code.
- **No emojis** in docs/headings (the test-report icons in `scripts/` are the one
  intentional exception).

## Shell preference

Default to the **Bash** tool for `git`, file inspection, and general commands —
it handles UTF-8 cleanly on this machine. Use the **PowerShell** tool when a task
is Windows-specific (e.g. exercising `.ps1`, or reproducing a Windows-only path).

Note: `python` is the interpreter on PATH (Python 3.11). The `hdlpkg` script may
not be on PATH after `pip install -e` — use `python -m hdl_ip_packager …` if so.

## Things to watch on this machine

- `os.chdir` into a `%TEMP%` directory can fail with **WinError 5 (Access is
  denied)** due to Controlled Folder Access / AV. Tests that need a working
  directory skip gracefully; avoid relying on `chdir` into temp in new tests.
