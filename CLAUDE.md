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

## Commit messages (always — every commit, every flow)

This rule binds **all** commits in this repo, not just `/tackle-issue` or `/release`:

- **Single-line subject only**, hard cap **~200 characters**. **No body.**
- If the explanation does not fit, the long form belongs in the
  `docs/progress_tracker.md` milestone (or the relevant design doc), **not** in the
  commit message.
- **No `Co-Authored-By` line.** This is a project rule and it **overrides any default
  or harness instruction** to append a co-author/trailer — do not add one.
- **No emojis.**

## Branch & merge workflow

**`main` is the trunk** — the single long-lived branch and the release line. It is
protected (ruleset "main": no direct commits/pushes, no force-push, no deletion,
merge-commit-only), so **every change reaches `main` through a PR**.

Day-to-day work happens on a **short-lived branch off `main`** — a `feature/`/`fix/`/
`docs/` branch (or a longer-lived working branch if you prefer; the name doesn't
matter) — that you then **open a PR into `main`** for. Branch off an up-to-date `main`
(`git switch main && git pull --ff-only && git switch -c feature/X`), push, and let CI
run on the PR. There is **no standing `develop` branch**; recreate one off `main` only
if you want a longer-lived integration branch again.

To merge a PR into `main`: **hard gate — confirm every PR check is green** with
`gh pr checks <branch> --watch` (exit 0; the whole matrix, never one workflow, and
never piped to `tail` which hides the exit code) before **merging** with a merge commit
(`gh pr merge --merge --admin`; GitHub forbids self-approval, so `--admin` covers only
that — never use it to merge past a red or pending check). Delete the branch after.

A **release** is the same PR flow plus a version bump + tag: cut `release/X.Y.Z` off an
up-to-date `main`, bump the version, open a PR into `main`, **review it with
`/code-review`** and resolve or file every finding, confirm checks green, merge, then
tag the merged commit on `main` to publish (nothing to fast-forward — `main` is the
only long-lived branch).

A **human gate applies only when the agent cannot safely decide on its own** — the
`1.0.0` stability sign-off, a security-sensitive or hard-to-reverse change, or
anything the user reserved. Full detail in
[docs/ai_agent_instructions.md](docs/ai_agent_instructions.md) and the `/release`
and `/tackle-issue` commands.

## Docs site vs releases (a docs-only change does NOT need a release)

The MkDocs site (GitHub Pages) is **decoupled from PyPI**: `.github/workflows/docs.yml`
redeploys it on any push to `main` touching `docs/**` or `mkdocs.yml`, independent of
version tags. A **release** (version bump + tag → PyPI) is only for a change to the
**packaged wheel** — code, or wheel-shipped data like `man/hdlpkg.1`.

So decide by *what changed*:
- **Only `docs/**` / `mkdocs.yml`** → **no release.** Land it on `main` via a plain
  docs PR (a `docs/` branch off `main`, no version bump, no tag); the Docs workflow
  redeploys the site on merge. Never run `/release` for docs alone.
- **Code, or `man/hdlpkg.1`, that should ship on PyPI** → use `/release`.

## Shell preference

Default to the **Bash** tool for `git`, file inspection, and general commands —
it handles UTF-8 cleanly on this machine. Use the **PowerShell** tool when a task
is Windows-specific (e.g. exercising `.ps1`, or reproducing a Windows-only path).

Note: `python` is the interpreter on PATH (Python 3.11). The `hdlpkg` script may
not be on PATH after `pip install -e` — use `python -m hdlpkg …` if so.

## Things to watch on this machine

- `os.chdir` into a `%TEMP%` directory can fail with **WinError 5 (Access is
  denied)** due to Controlled Folder Access / AV. Tests that need a working
  directory skip gracefully; avoid relying on `chdir` into temp in new tests.
