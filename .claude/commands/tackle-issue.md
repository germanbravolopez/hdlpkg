---
description: Pick up and ship an open item from docs/progress_tracker.md — read, plan, implement, test, update docs, commit on develop. Use for "tackle X", "fix Y", "do the next roadmap milestone".
argument-hint: <issue or roadmap item>
---

# /tackle-issue — Resolve an Open Issue from the Progress Tracker

End-to-end workflow for picking up an open item from `docs/progress_tracker.md` and shipping it. Encapsulates the loop we run for every change: read → plan (if non-trivial) → implement → test → update docs → commit.

Use when the user says things like "tackle X", "let's fix Y", "move on to Z", "do the next roadmap milestone" — where the work maps to an entry in the **Roadmap**, **Blocking Issues**, or **Open Non-Blocking Issues** section of `docs/progress_tracker.md`.

---

## Steps

### 1. Locate the issue

- Read `docs/progress_tracker.md` and find the item the user named. It should be in **Roadmap (M1…M8)**, **Blocking Issues**, or **Open Non-Blocking Issues** — anything in **Completed Milestones** is already done.
- The full entry contains the problem statement, sometimes a proposed approach, and the affected files. **Read it in full before touching code** — the description usually answers the design questions you would otherwise ask.
- If the item touches a subsystem you don't have in context, read its section in `docs/architecture.md` first.

### 2. Decide on the approach

- **Small / mechanical** (rename, find-and-replace, single-function edit): just do it.
- **Medium** (one module, clear intent): state the plan in 1–3 sentences before implementing, but don't block on confirmation.
- **Large or with open design choices** (multiple modules, new subsystem, data-model changes, CLI/UX-affecting changes): use `AskUserQuestion` to surface the choices first, OR write out the plan and ask for go-ahead. Don't sprawl into a refactor the user didn't agree to.

If the tracker lists two approaches (e.g. "minimal option" vs "architectural option"), pick the user's stated preference. If unstated, default to the simpler one and call out the tradeoff.

### 3. Implement

- **Apply `/coding-guidelines` to every new identifier you introduce.** Read the skill file (`.claude/commands/coding-guidelines.md`) at the start of implementation if you haven't already this session. English everywhere — names, comments, docstrings, docs.
- **Types are mandatory on `src/` (mypy `--strict`).** Model data as `@dataclass(frozen=True)` with `parse` / `from_*` classmethods. Don't introduce `Any` or untyped public functions.
- **Purity by default.** Keep logic free of I/O; do filesystem/network only in the CLI and registry layers. This is the testability rule (step 6 depends on it) — extract the pure core as a free function so a unit test can call it directly, and keep the CLI/registry wrapper thin. See `.claude/commands/coding-guidelines.md` and `docs/architecture.md` §Testing.
- **Errors derive from `HdlPackagerError`** (`src/hdlpkg/exceptions.py`). Never `print` errors in library code — raise; the CLI layer is the only place that formats them for the user.
- **Keep inline comments few and short.** Default to none; add a one-or-two-line comment only at a critical/non-obvious spot, and never restate the docs milestone you write in step 5 inside the code. Longer blocks are reserved for file/module headers and test files.
- Read existing call sites before changing signatures — `Grep` first, edit second.
- Track multi-step work with `TodoWrite`. Mark steps complete as you finish them.
- Don't bundle unrelated cleanup into the change unless the user asked. Dead code touched by the refactor is fair game; dead code in untouched modules is a separate task.
- **PEP 8 via `ruff format`, line length 100.** Be precise the first time — the gates in step 4 are fast, but clean code passes them on the first run.

### 4. Run the quality gates

Every behaviour ships with the gates green. From the repo root:

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

(`python -m pytest` if the `pytest` script isn't on PATH; the project's interpreter is `python` = Python 3.11.)

- `pytest` → all passing, no skips that hide your change. See step 6 — covering the change is part of the change.
- `ruff check .` → lint clean. Apply autofixes with `ruff check --fix .` where safe, but read what it changed.
- `ruff format --check .` → run `ruff format .` to apply if it reports diffs.
- `mypy src` → no errors. `--strict` is configured in `pyproject.toml`; don't silence with `# type: ignore` unless you justify it in the commit.

All four green is a hard prerequisite for the commit. If a gate fails, fix the code (or the test, if its expectation was genuinely wrong — say which in the commit) and re-run; never commit red or with a skipped test that hides the change.

### 5. Update docs (run the `/update-docs` command)

Work the `/update-docs` checklist; at minimum:

- **`docs/progress_tracker.md`** — almost always.
  - Move the item out of Roadmap / Blocking / Open Non-Blocking into **Completed Milestones** (newest at top), under a `### <topic> — <Month Year>` heading. Use absolute dates.
  - Format: `- [x] **Title**: what was done, why, key files. Include rationale that wasn't obvious from the diff.`
  - Update **Current Status** (stage + "Next") if the headline state changed. If you finished a roadmap milestone (M1…M8), say so and note what's next.
  - Never delete history — move stale entries to **Archive**. Don't paste the original issue text; write fresh prose reflecting the actual change.
- **`docs/architecture.md`** — when a module, the data model, or a data-flow path changed. Flip the relevant **(planned)** → **(implemented)** in the module map.
- **`docs/INDEX.md`** — when files, tests, CLI commands, concepts, or glossary terms were added/renamed/removed.
- **`README.md`** (repo root) — when user-visible behaviour, install, or CLI changed. Skip for purely internal changes.
- **`tests/README.md`** — when the test layout, markers, or fixtures changed.
- New module? Add `docs/modules/<name>.md` and register it in `docs/README.md` + `docs/INDEX.md`.

Do NOT update `docs/ai_agent_instructions.md` unless the change alters the agent's onboarding picture (status table, file map, agent rules). Skip files that have nothing to do with the change — don't pad the diff.

### 6. Coverage gate (part of step 4, called out here)

A passing import proves the code loads; the test suite is what proves the change does what it claims and that nothing it touched regressed. **Covering the change is part of the change, not optional** — it is enforced in CI.

- **Add or update a test for every behaviour you changed or added** in `tests/unit/` (pure logic) or `tests/integration/` (CLI flow). Update an existing suite when the module already has one; create a new file otherwise (`tests/unit/test_<module>.py`), and cover the error paths too — every behaviour ships with tests for its failure modes.
- **Make it testable** (you should have done this in step 3): unit-test the pure core. If the logic is filesystem/registry-coupled, the seam belongs in a library function so a test can call it without real I/O; use `tmp_path` / fixtures in `tests/conftest.py` for the thin I/O wrapper.
- Watch the Windows gotcha from `CLAUDE.md`: `os.chdir` into a `%TEMP%` dir can fail with WinError 5 (Controlled Folder Access). Don't write tests that rely on `chdir` into temp; skip gracefully if one truly must.
- If a change genuinely cannot be unit-tested (pure CLI wiring), state that explicitly in the commit + milestone and note what a future harness would need — don't silently skip coverage.

### 7. Commit (on `develop` — no PR)

Normal work lands on **`develop`**, the working branch — **no PR** (a PR is only for
a release, `develop` → `main`; see `/release`). `main` is the protected release line;
never commit on it directly.

- **Commit on `develop`** (or a short-lived `feature/`/`fix/`/`docs/` branch you then
  merge into `develop`). The accumulated `develop` diff is reviewed at the next
  release, so a per-change PR is not needed.
- **Commit message**: follow the canonical rule in [CLAUDE.md](../../CLAUDE.md)
  ("Commit messages") — single-line subject, hard cap ~200 characters, no body, **no
  `Co-Authored-By` line**, no emojis. If the explanation doesn't fit, the long-form
  belongs in the `docs/progress_tracker.md` milestone you wrote in step 5.
- **Stage only the files this change touched.** Never `git add -A` / `git add .` —
  pre-existing unrelated edits must not ride along. If you find such edits, leave
  them alone and call them out in your final message.
- **Never `--amend`** a commit the user has already seen or that has been pushed.
  Create a new commit instead.
- **Push `develop`.** CI runs on the push.

After the commit:

- Run `git status` to confirm no remaining modifications to the files this change
  touched (pre-existing unrelated `M` files are fine — flag them, don't fold them in).
- Output the commit hash and a short summary.

**Defer to a human gate only when you cannot safely decide on your own** — a
security-sensitive or hard-to-reverse change, or anything the user reserved. There,
stop and surface it rather than committing.

---

## When NOT to use this command

- The user asks a question (no change implied).
- The work spans multiple unrelated issues — handle one at a time.
- The "issue" is really a design discussion that hasn't crystallized into the tracker yet.
- The user explicitly scopes it down ("just update the doc", "only run the tests") — honor that; this command is the *default* shape for "tackle issue X", not a mandatory template.
