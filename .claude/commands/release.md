# /release — Cut a Release X.Y.Z End-to-End

Executes this project's tag-driven release flow: bump the version, make the gates
green, record the release in the tracker, commit, then **tag** the commit — which
triggers [`.github/workflows/release.yml`](../../.github/workflows/release.yml) to
build the wheel + sdist, publish them to PyPI via OIDC trusted publishing, and create
a **GitHub Release** for the tag (a short summary from the `docs/progress_tracker.md`
entry + a link to the PyPI page, with the dists attached). The build/publish steps
are never run by hand; this skill drives the bump/review/merge/tag, pushes, and then
watches the workflows to green.

Use when the user says "release X.Y.Z", "ship X.Y.Z", "cut X.Y.Z", or "do the
release for milestone M_n". Reject if no version is given — ask for it.

The **Release plan** section of [docs/progress_tracker.md](../../docs/progress_tracker.md)
is the source of truth for *which* version maps to *which* milestone(s). If a step
here ever drifts from that plan or the README "Releasing" section, those win;
update this skill afterwards.

---

## Preconditions (check before doing anything)

1. **A release is the one flow that uses a PR.** Normal work lives on `develop` (the
   working branch, committed to directly — no PR). A release brings `develop`'s
   accumulated work onto `main`: `main` is governed by the repository ruleset named
   "main" (no direct commits/pushes, no force-push, merge-commit-only, one approving
   review with last-push approval). The release bump lands on `main` through a
   `release/X.Y.Z` PR (cut off `develop`) that the agent **reviews with `/code-review`
   and then merges** with `gh pr merge --merge --admin` (step 7 — `--admin` bypasses
   the self-approval the ruleset would otherwise require); the `X.Y.Z` tag is then
   created on the resulting merge commit on `main`, and `develop` is fast-forwarded to
   it. Start from an up-to-date `develop` (`git switch develop && git pull`).
2. **Working tree is clean** (`git status` shows nothing to commit). If dirty, ask
   whether to commit, stash, or abort — never fold stray edits into the release.
3. **Version is SemVer `X.Y.Z`** (or a pre-release `X.Y.Z-rc.N`), with **no** `v`
   prefix — tags are bare. It must be **greater** than the current
   `[project].version` in `pyproject.toml`. If equal or lower, abort.
4. **The version matches the Release plan.** Confirm the milestone(s) this version
   ships (per the plan table) are actually done and live in **Completed Milestones**.
   Releasing mid-milestone is not a release moment — finish the milestone first.
5. **No existing `X.Y.Z` tag.** `git tag -l X.Y.Z` must be empty. (PyPI is
   immutable and append-only — a version can never be re-published, so a clean cut
   needs an unused number.)
6. **`1.0.0` requires explicit user sign-off.** `1.0.0` is the stability commitment,
   gated on the criteria in the Release plan (frozen `ip.toml`/`ip.lock` formats,
   stable CLI + registry protocol, a third-party publish/consume, an `rc` soak). Do
   **not** tag `1.0.0` autonomously — present the checklist and get a go-ahead. If
   formats are still moving, ship it as the next `0.y.0` instead.

If any precondition fails, stop and surface it — don't paper over it.

---

## Steps

### 1. Pre-flight the tracker + docs

Before bumping, make the working tree release-ready (run the `/update-docs`
checklist; stage, don't commit yet):

- [ ] **`docs/progress_tracker.md`** — every milestone in this release is in
  **Completed Milestones** with a real entry (the tracker is the changelog source;
  there is no separate release-notes file). **Current Status -> Next** points at the
  next milestone.
- [ ] **`docs/architecture.md` / `docs/INDEX.md` / `README.md` / `tests/README.md`**
  — reflect anything user-visible/structural that landed since the last tag. No-op
  if nothing relevant changed.

### 2. Bump the version (two files, kept in lockstep)

The version lives in **two** places and they must match (the publish guard checks
`pyproject.toml`; `--version` reads `__init__.py`):

- `pyproject.toml` -> `[project].version = "X.Y.Z"`
- `src/hdl_ip_packager/__init__.py` -> `__version__ = "X.Y.Z"`

Sanity-check they agree: `python -m hdl_ip_packager --version` prints `hdlpkg X.Y.Z`.

### 3. Make the quality gates green (hard gate)

From the repo root, all four must pass — this is the same suite CI runs:

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

If any gate fails, **stop**, fix on `main`, and rerun. Never tag red.

### 4. Verify the release guard

The publish job fails the build if the tag and packaged version disagree. Confirm
locally first so a bad tag never reaches CI:

```bash
python scripts/check_release_version.py --ref refs/tags/X.Y.Z
```

It must print `OK: tag matches packaged version X.Y.Z`.

### 5. Record the release in the tracker

In `docs/progress_tracker.md`:

- Update the **Version** line under Current Status to `X.Y.Z` with a one-line
  capability summary.
- Add a `### Release X.Y.Z — <Month Year>` entry at the **top** of Completed
  Milestones: a one-bullet `- [x]` noting what the release unlocks and that
  `pyproject.toml` + `__init__.py` were bumped. (Absolute dates; never delete
  history.)

### 6. Commit the bump on a `release/X.Y.Z` branch (off `develop`) and open a PR

`main` is protected (ruleset "main"), so the bump cannot be pushed to `main`
directly. Branch off `develop` (so the PR carries develop's accumulated work plus the
bump), commit, and open a PR into `main`. Stage only the bump + tracker/doc files.
Single-line subject, project style, **no** `Co-Authored-By`, no emojis:

```bash
git switch develop && git pull --ff-only
git switch -c release/X.Y.Z
git commit -m "Release X.Y.Z: <one-line summary of what this release ships>"
git push -u origin release/X.Y.Z
gh pr create --base main --title "Release X.Y.Z: <summary>" --body "<summary>"
```

### 7. Review the PR with `/code-review`, resolve findings, then merge

A release merge is the **last** point at which a regression can be caught before it
ships to PyPI under a tagged, **immutable** version (a published version can never be
re-used). Before merging, **review the PR yourself** at high effort — not the default
level. A release diff is usually wider than a single feature PR (the branch may
bundle several milestones), so the broader-coverage tier is appropriate even though
it may surface lower-confidence findings:

```
/code-review high
```

This reviews the current `release/X.Y.Z` branch diff against `main`. `/code-review
high <PR#>` targets the PR explicitly; `ultra` runs the deeper cloud multi-agent
variant if a particular release ever warrants it. Runs locally.

**Resolve every finding before merging** — this is a hard gate:

- **Genuine bugs / regressions / release-blockers, and anything fixable within this
  release's scope:** fix them on the `release/X.Y.Z` branch now, commit, and push
  (the PR updates automatically). Re-run the gates (step 3) — and the review itself
  if the fixes are non-trivial. Err on the side of fixing anything touching the
  high-blast-radius areas: **resolver** correctness, **lockfile/digest** integrity,
  the cache's **verify-on-read**, **packaging** path-traversal guards, and the
  **registry** protocol.
- **Findings that cannot be fixed before this merge** (out of the release's scope,
  pre-existing, or needing external services): record them as new entries in
  `docs/progress_tracker.md` **Open Non-Blocking Issues**, stage that doc, and fold
  it into the release branch — do **not** block the release on them.

Do not proceed to the merge until **every** finding is either fixed or filed.

**Then merge the PR — but only once EVERY check is green. This is a hard gate.**
Wait for **all** PR checks (the full CI matrix — every OS/Python job, Docs, anything
else — not a single workflow run) to pass. Use `gh pr checks`, which exits non-zero
if any check fails or is still pending:

```bash
gh pr checks release/X.Y.Z --watch    # do NOT pipe to tail / a pager — that hides the exit code
echo "checks exit: $?"                 # must be 0 before you merge
```

**If any check is red or pending, STOP — do not merge:**
- **A real failure** (test/lint/type error): fix it on the branch, push, and re-watch.
- **A transient infra flake** (e.g. an `actions/setup-python` network error that
  leaves the `Install`/`Test` steps *skipped*, not failed): re-run only the failed
  run and re-watch until it is genuinely green —
  `gh run rerun <run-id> --failed` then `gh pr checks release/X.Y.Z --watch`.
- **Never** use `--admin` to merge past a failing or pending check. `--admin` exists
  only to satisfy the **self-approval** the ruleset requires (you cannot approve your
  own PR); it must never be the reason a red check reaches `main`.

Only when `gh pr checks` has exited `0` (all green), merge with a **merge commit**
(ruleset "main": `allowed_merge_methods: ["merge"]`, squash/rebase disabled). The
`--admin` flag covers only the required-review / last-push approval (it logs a
"bypassed rule violations" entry — expected for an agent-driven release):

```bash
gh pr merge release/X.Y.Z --merge --admin --delete-branch
```

`--merge` is mandatory — `--squash`/`--rebase` defeat the "release = one point on
`main`" convention. If `gh` cannot merge cleanly (protected-branch failure, conflict),
**stop and surface it** — do not paper over it.

### 7b. Tag the merged `main` (the tag push is the publish trigger)

Fast-forward local `main` to the merge commit and tag it (bare tag, no `v` prefix),
then push the tag:

```bash
git switch main && git pull --ff-only
python scripts/check_release_version.py --ref refs/tags/X.Y.Z  # re-confirm on merged main
git tag -a X.Y.Z -m "Release X.Y.Z - <summary>"
git push origin X.Y.Z

# Carry the release merge back onto the working branch so develop is not left behind.
git switch develop && git merge --ff-only main && git push origin develop
```

The `X.Y.Z` tag fires `release.yml`: the **build** job runs the guard + `python -m
build`, then the **publish** job uploads the wheel + sdist to PyPI via OIDC trusted
publishing. (One-time setup already done: the repo is a PyPI trusted publisher with
a `pypi` environment.)

### 8. Watch the workflows to green (always — don't skip)

Block on the workflows the push triggered; never declare a release done on a red or
still-running run:

```bash
# Release (build + publish to PyPI)
gh run watch "$(gh run list --workflow Release --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status

# CI (tests/ruff/mypy on the main push) and Docs (Pages) should also be green
gh run list --limit 5
```

`--exit-status` makes a failed run a non-zero exit. **If a run fails**, read the
log (`gh run view <id> --log-failed`) and diagnose with the user. Do **not** delete
the tag without asking — the commit and tag are already public, and the PyPI
version (if the publish step got that far) can't be reused. Fix forward.

### 9. Confirm the PyPI publish

The PyPI JSON API lags the workflow by a cache window; poll until the new version
appears rather than assuming success from the green workflow alone:

```bash
until curl -s "https://pypi.org/pypi/hdl-ip-packager/json?$(date +%s)" | grep -q '"X.Y.Z"'; do sleep 5; done
curl -s "https://pypi.org/pypi/hdl-ip-packager/json?$(date +%s)" | python -c "import sys,json; d=json.load(sys.stdin); print('latest:', d['info']['version']); print('files:', [f['filename'] for f in d['releases']['X.Y.Z']])"
```

Confirm the wheel + sdist are both listed. Surface the release URL
(`https://pypi.org/project/hdl-ip-packager/X.Y.Z/`).

### 10. Post-release housekeeping

- `git status` on `main` is clean and on the merge commit that landed the release PR.
- Confirm the **GitHub Release** the `github-release` job created (`gh release view
  X.Y.Z`): its body carries the tracker summary + the PyPI link, with the wheel +
  sdist attached. (The job runs `gh release create` from the workflow — never create
  the release by hand.)
- The merged `release/X.Y.Z` branch is auto-deleted by `gh pr merge --delete-branch`
  (step 7); delete it manually only if the merge left it behind.
- Confirm `develop` was fast-forwarded to `main` (step 7b) so the working branch
  carries the release commit; future work continues on `develop`.
- State the published version, the PyPI + GitHub Release URLs, and what the next
  milestone/release is (from Current Status -> Next).

---

## Rules

- **Tag-driven publish.** Never run `python -m build`/`twine`/`gh release` by hand —
  pushing the `X.Y.Z` tag is the only publish path. The artifacts must come from the
  tagged commit on `main`.
- **Two version files in lockstep.** `pyproject.toml` and `__init__.py` must always
  agree; the guard only checks the former, so a mismatch ships a mislabeled wheel.
- **Release at plan boundaries only.** Cut a release at the capability groupings in
  the Release plan (e.g. 0.2 = M1+M2), not after every milestone.
- **PR-based, merge-commit only.** The release bump reaches `main` via a
  `release/X.Y.Z` PR merged with a merge commit (ruleset "main"); never push the
  bump straight to `main`. The agent **reviews the PR with `/code-review` (step 7)**,
  resolves or files every finding, then merges with `gh pr merge --merge --admin`
  (GitHub forbids self-approval, so `--admin` bypasses the required-review check and
  logs it). The `X.Y.Z` tag is created on the merged `main` afterwards.
- **`1.0.0` is a sign-off, not a default.** Get explicit user confirmation against
  the stability gate; never tag it autonomously.
- **Resolve review findings before merge.** Every `/code-review` finding is either
  fixed on the release branch or filed in Open Non-Blocking Issues before the merge —
  never merge with an open, unaddressed finding.
- **Green CI is a hard gate before merge.** Verify **all** PR checks pass with
  `gh pr checks <branch> --watch` (exit 0) before merging — the whole matrix, not one
  workflow. Never pipe the watch to `tail`/a pager (it hides the exit code), and never
  use `--admin` to merge past a red or pending check (`--admin` is only for the
  self-approval requirement). A flaky infra failure is re-run to green
  (`gh run rerun <id> --failed`), not bypassed.
- **Stop on the first failure** — dirty tree, red gate, guard mismatch, tag
  conflict, a merge that won't go cleanly, a red or pending PR check, failed workflow.
  Surface it and wait.
- **No `Co-Authored-By`, no emojis** (project rules).

---

## When NOT to use this skill

- Just bumping the version without releasing — do that one edit, don't tag.
- Mid-milestone, or before the milestone's work is committed and the gates are green.
- A docs-only or tracker-only change — edit directly; a release is a tag + publish.
