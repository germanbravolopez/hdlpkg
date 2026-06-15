# Migration plan — rename `hdl-ip-packager` -> `hdlpkg`

**Status:** **accepted** (decisions in [§Decisions](#decisions-recorded-2026-06-15)); the
in-repo sweep starts now. **When:** before 0.13.0 feature work, and before 1.0.0 — while
still pre-1.0, so the import-name break carries no stability-promise cost. **Confirmed:**
`hdlpkg` is available on PyPI. **The rename ships as `hdlpkg` 0.13.0** (rename only); the
git/IP-XACT work moves to 0.14.0.

## Why now
The CLI command is already `hdlpkg`; the distribution (`hdl-ip-packager`) and import
package (`hdl_ip_packager`) lag behind the brand. Doing it pre-1.0 means no frozen-API
break; doing it before 0.13.0 means the git/IP-XACT work lands on the final names.

## What changes vs. what doesn't

**Changes (two names):**
- **Import package**: `hdl_ip_packager` -> `hdlpkg` (the `src/hdl_ip_packager/` directory;
  ~314 references across ~91 files: imports, `python -m hdl_ip_packager`, tests, scripts,
  docs).
- **Distribution / PyPI project**: `hdl-ip-packager` -> `hdlpkg` (~35 references: pyproject
  `[project].name`, `pip install` docs, URLs).
- **GitHub repo**: `germanbravolopez/hdl-ip-packager` -> `germanbravolopez/hdlpkg` (+ Pages
  URL, badges, the sibling repos' CI checkout refs).
- **PyPI trusted publishing**: a new publisher entry for the `hdlpkg` project (owner/repo,
  `release.yml`, `pypi` environment).

**Does NOT change (important):**
- The **CLI command** stays `hdlpkg` — end users typing commands see nothing change.
- **`ip.toml` / `ip.lock` formats** — the tool's package name is not embedded in them, so
  **no user-project migration**; existing lockfiles keep working untouched.
- Only API consumers who `import hdl_ip_packager` or `pip install hdl-ip-packager` in
  scripts/CI must switch — addressed by the shim below.

## Sequencing (in-repo first, external last)

1. **In-repo sweep** (reversible, gate-verified — the bulk):
   - `git mv src/hdl_ip_packager src/hdlpkg`.
   - Replace `hdl_ip_packager` -> `hdlpkg` everywhere (imports, `python -m`, tests,
     scripts, docs), and `hdl-ip-packager` -> `hdlpkg` for the distribution name (leaving
     GitHub URLs to the repo-rename step, or updating them in lockstep if the repo is
     renamed first).
   - `pyproject.toml`: `[project].name = "hdlpkg"`, `packages = ["src/hdlpkg"]`, the
     `shared-data` man-page entry, the entry point (`hdlpkg = "hdlpkg.cli:main"`),
     `[tool.coverage.run] source`, mypy `files`, sdist `include`.
   - Regenerate the man page; re-green `pytest` / `ruff` / `mypy`.
   - Update the auto-memory note ("Project rename") to record the second rename.
2. **Sibling repos** (`hdlpkg-consumer-demo`, `hdlpkg-livetest`): the `../hdl-ip-packager`
   relative paths, `python -m hdl_ip_packager` -> `python -m hdlpkg`, the CI `checkout`
   of `germanbravolopez/hdl-ip-packager`, and `pip install` lines. (Both sibling repos are
   already named `hdlpkg-*`, so only the references change.)
3. **GitHub repo rename** `hdl-ip-packager` -> `hdlpkg` (**user action** — needs repo
   admin). GitHub auto-redirects old clone/URL paths; update Pages URL + badges + the
   sibling CI `repository:` fields.
4. **PyPI** (**user action** — needs PyPI account): register the `hdlpkg` project via
   trusted publishing (owner/repo + `release.yml` + `pypi` environment); the first
   `hdlpkg` release is published by the tag, exactly as today.
5. **Deprecation shim** (recommended): publish a final `hdl-ip-packager` release that is an
   empty package depending on `hdlpkg` with a deprecation notice in its README/description,
   so `pip install hdl-ip-packager` keeps resolving and points users to `hdlpkg`. (The old
   project's `0.1.0`–`0.12.0` stay immutable; the shim is one extra version.)
6. **Release** the renamed package (via `/release`) and watch it to green on PyPI under the
   new name.

The agent does 1–2 and 6; the user does 3–4 (and triggers 5's publish via the tag). The
in-repo sweep is fully reversible and verifiable before any external move.

## Decisions (recorded 2026-06-15)

1. **Version of the rename release: clean split.** The first `hdlpkg` release is
   **`0.13.0`** = "identical to `hdl-ip-packager` 0.12.0, renamed" (no features); the
   git/IP-XACT work moves to **`0.14.0`**.
2. **Old-distribution shim: yes.** Publish a final `hdl-ip-packager` release that is an
   empty package depending on `hdlpkg` with a deprecation notice, so
   `pip install hdl-ip-packager` keeps resolving to the new code.
3. **Import-name back-compat: clean break.** Remove `hdl_ip_packager` entirely; only
   `import hdlpkg` works. Documented in the 0.13.0 release notes.
4. **GitHub repo rename: up front.** The repo is renamed to `hdlpkg` first (user action),
   and the in-repo sweep updates all URLs/CI refs to the new name in lockstep.

### Who does what
- **Agent**: in-repo sweep (1), sibling repos (2), the `/release 0.13.0` flow (6), and
  prepares the shim package.
- **User (needs admin/credentials)**: rename the GitHub repo (3); register the `hdlpkg`
  PyPI project as a trusted publisher (4); the shim's PyPI project + its trusted publisher
  (5). The agent will give exact steps when each is reached.
