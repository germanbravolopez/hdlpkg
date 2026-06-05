# /update-docs — Update Project Documentation

Run this after every feature, fix, refactor, or new insight. Good docs save the
next agent (and you) time. Work through the checklist in order; skip a step only
if nothing in that file changed.

## Checklist

### 1. `docs/progress_tracker.md` — almost always update this
- Move the item you worked on out of Roadmap / Open Issues into **Completed
  Milestones** (newest at the top), with a dated entry: what you did, which files.
- Group completed entries under a `### <topic> — <Month Year>` heading.
- Update **Current Status** (stage + "Next") if the headline state changed.
- If you finished a roadmap milestone (M1…M8), say so and note what's next.
- Never delete entries — move stale ones to **Archive**. Use absolute dates.

### 2. `docs/architecture.md` — when a module, the data model, or data flow changed
- Flip the relevant **(planned)** to **(implemented)** in the module map.
- Update the data model / subsystem section for what you built.
- Update the data-flow section if the `info`/resolve/etc. path changed.
- If a subsystem section grows large, split it into `docs/modules/<name>.md`.

### 3. `docs/INDEX.md` — when files, concepts, commands, or terms were added
- Add new source files / tests / CLI commands to their tables.
- Add new glossary terms and topic→file entries.

### 4. `README.md` (repo root) — when user-visible behaviour/install/CLI changed
- Update Features, Usage, Requirements, or the workflow as needed.
- Skip for purely internal changes (refactor, docs-only, bugfix with no behaviour
  change).

### 5. `tests/README.md` — when the test layout, markers, or fixtures changed
- Document new markers, fixtures, or directories.

### 6. New module? Add `docs/modules/<name>.md`
- Purpose, source files, public interface, integration notes — then register it
  in `docs/README.md` and `docs/INDEX.md`.

---

## Rules

- **English only.** **No emojis** in doc/heading text.
- **No duplication** — if content exists elsewhere, link to it instead of copying.
  Long-form lives in docs; code carries a one-line pointer.
- **Most important content first** — keep the first ~100 lines of any doc the
  essential part.
- **Never delete** progress-tracker history — archive it.
- **Respect the size limits** in `docs/ai_agent_instructions.md`; split when over.
- After updating docs, make sure the quality gates still pass (`pytest`, `ruff`,
  `mypy`) — docs and code land together.
