# Documentation — HDL IP Packager

Navigation index for the `docs/` folder. For the project-wide quick-find
reference (every file, concept, and topic) see [INDEX.md](./INDEX.md).

---

## Structure

```
docs/
├── README.md                     (this file - docs folder navigation)
├── INDEX.md                      (project-wide quick-find: files, concepts, topics)
├── user_guide.md                 (start here if you are new - what it does + a walkthrough)
├── ai_agent_instructions.md      (agent/contributor onboarding - start here)
├── architecture.md               (module map, data model, subsystem designs, data flow)
├── progress_tracker.md           (status + ordered roadmap; read before working)
├── modules/                      (the user manual: one page per module + the CLI)
│   └── README.md                 (module-reference index)
└── research/
    └── state_of_the_art.md       (survey of package managers + HDL tools; design rationale)
```

The per-module reference (a "user manual") lives under `docs/modules/`, one page per
module plus the CLI command reference — see [modules/README.md](./modules/README.md).
When a new module lands, add its page there and register it in that index and in
[INDEX.md](./INDEX.md).

---

## Core documentation

| Document | Purpose | Read time |
|----------|---------|-----------|
| [user_guide.md](./user_guide.md) | **New here? Start here** — what the tool does and a hands-on walkthrough | 8 min |
| [modules/](./modules/README.md) | The user manual: per-module reference + the full CLI command reference | As needed |
| [ai_agent_instructions.md](./ai_agent_instructions.md) | Briefing, file map, coding + testability rules, agent obligations | 6 min |
| [architecture.md](./architecture.md) | How it is built and how it grows | 12 min |
| [progress_tracker.md](./progress_tracker.md) | What is done, the roadmap, open issues | 5 min |
| [research/state_of_the_art.md](./research/state_of_the_art.md) | Why the design is what it is | 15 min |
| [INDEX.md](./INDEX.md) | Find any file, concept, or topic | As needed |

## Related (outside docs/)

| Document | Purpose |
|----------|---------|
| [../README.md](../README.md) | Project overview, install, usage, development workflow |
| [../tests/README.md](../tests/README.md) | Test suite layout and how to add tests |
| [../CLAUDE.md](../CLAUDE.md) | Entry point for the Claude Code agent |

---

## Adding documentation for a new module

1. Create `docs/modules/<module-name>.md` with: purpose, source files, public
   interface, and integration notes.
2. Register it in the tables in this file and in [INDEX.md](./INDEX.md).
3. If it implements a roadmap milestone, update [progress_tracker.md](./progress_tracker.md)
   (move the item to Completed) and flip the relevant **(planned)** to
   **(implemented)** in [architecture.md](./architecture.md).
