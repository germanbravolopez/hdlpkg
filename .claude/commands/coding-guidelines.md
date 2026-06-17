---
description: hdlpkg code style, typing, and testability rules — Python 3.11+, ruff format (line 100), mypy --strict on src/, frozen dataclasses with parse/from_* classmethods, I/O confined to the CLI and registry layers. Apply when writing or changing code under src/.
---

# /coding-guidelines — Code Development Guidelines

Apply these to all new code in this project. When modifying existing code, follow
them for the new parts without gratuitously renaming legacy identifiers.

This is the long-form version of the summary in [CLAUDE.md](../../CLAUDE.md) and
[docs/ai_agent_instructions.md](../../docs/ai_agent_instructions.md). The
implemented modules (`version.py`, `vlnv.py`, `manifest.py`) are the reference —
match their style.

---

## Language & formatting

| What | Rule |
|------|------|
| Python version | 3.11+ (use modern syntax: `X | Y` unions, `tuple[...]`, `match` where it reads well) |
| Formatting | `ruff format` (PEP 8, line length 100). Run before committing. |
| Linting | `ruff check .` must pass (rules: E, F, I, UP, B, SIM, RUF). |
| Language | **English** for identifiers, comments, docstrings, errors, logs. |
| Encoding | Plain ASCII in source; no em-dashes/curly quotes/ellipsis in code. |

## Naming

| Construct | Style | Examples |
|-----------|-------|----------|
| Functions, variables, modules | `snake_case` | `parse_manifest`, `version_str` |
| Classes / dataclasses | `PascalCase` | `Version`, `VersionConstraint`, `Vlnv` |
| Module constants | `UPPER_SNAKE_CASE` | `MANIFEST_FILENAME` |
| Internal helpers | `_leading_underscore` | `_parse_clause`, `_caret_upper` |
| Booleans / predicates | `is_` / `has_` / `can_` | `is_prerelease`, `matches_any` |

## Types — mandatory

- Annotate **every** function signature in `src/`. `mypy --strict` must pass.
- Prefer precise types over `Any`: `tuple[str, ...]`, `dict[str, object]`,
  `X | None`. Use `from __future__ import annotations` at the top of each module.
- Tests are exempt from the strict type gate (pytest fixtures make it noisy), but
  keep them readable.

## Structure & purity (the testability rule)

- **Keep parsing/logic pure** — no file/network I/O, no global mutable state.
  Do I/O only in `cli.py` and the (future) registry layer. If logic is hard to
  test, extract the pure decision into its own function and test that.
- Model data as **`@dataclass(frozen=True)`** value types: construct via a
  `@classmethod` `parse`/`from_*`, render via `__str__`.
- One responsibility per module; respect the acyclic dependency direction in
  [architecture.md](../../docs/architecture.md) (`exceptions ← version ← vlnv ←
  manifest ← {resolver, cli}`).
- Keep functions small (aim under ~40 lines); extract a named helper otherwise.

## Errors

- Raise a subclass of `HdlPackagerError` (add one in `exceptions.py` if needed).
- Error messages **name the offending input** (e.g. the bad field/segment).
- Never `print` for errors in library code — raise. The CLI turns exceptions into
  an `error: …` line + exit code 1. Never silently swallow an error.

## Docstrings & comments

- Every module: a docstring with purpose + key design notes (and a short example
  where it helps, as in `manifest.py`).
- Every public function/class: a one-line docstring stating the contract (what it
  returns, what counts as failure).
- Comment the **why**, not the what; one or two lines max. Long-form explanations
  go in `docs/`, with a one-line pointer in the code.

## Dependencies

- Keep **runtime** dependencies minimal — justify each new one in the PR and the
  progress tracker. Dev/test tools go in `[project.optional-dependencies].dev`.
- Prefer the standard library (e.g. `tomllib`, `pathlib`, `argparse`) before
  reaching for a package.

## CLI

- `cli.py` stays thin: parse args, delegate to library functions, return an exit
  code. No business logic there. New commands register in `build_parser` and set
  a `func`; planned commands report "not implemented" (exit 2).

## What NOT to do

| Forbidden | Reason |
|-----------|--------|
| I/O or global state in `version`/`vlnv`/`manifest`/`resolver` | Breaks purity and testability |
| `Any` where a precise type is known | Defeats the strict type gate |
| Bare `except:` / swallowing errors | Hides failures; always raise or log |
| `print` for errors in library code | Library raises; only the CLI prints |
| New runtime dependency without justification | Bloat + supply-chain surface |
| Committing code with failing `pytest`/`ruff`/`mypy` | The gates are the contract |
| Emojis in docs/headings | House style (test-report icons in `scripts/` excepted) |
