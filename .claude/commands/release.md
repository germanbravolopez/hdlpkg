# /release — Cut a Release X.Y.Z End-to-End

Executes this project's tag-driven release flow: bump the version, make the gates
green, record the release in the tracker, commit, then **tag** the commit — which
triggers [`.github/workflows/release.yml`](../../.github/workflows/release.yml) to
build the wheel + sdist and publish them to PyPI via OIDC trusted publishing. The
build/publish steps are never run by hand; this skill drives the bump/commit/tag,
pushes, and then watches the workflows to green.

Use when the user says "release X.Y.Z", "ship X.Y.Z", "cut X.Y.Z", or "do the
release for milestone M_n". Reject if no version is given — ask for it.

The **Release plan** section of [docs/progress_tracker.md](../../docs/progress_tracker.md)
is the source of truth for *which* version maps to *which* milestone(s). If a step
here ever drifts from that plan or the README "Releasing" section, those win;
update this skill afterwards.

---

## Preconditions (check before doing anything)

1. **Release via a PR, not a direct push.** `main` is governed by the repository
   ruleset named "main" (no direct commits/pushes, no force-push, merge-commit-only,
   one approving review with last-push approval). The release bump lands on `main`
   through a `release/X.Y.Z` PR that a human approves and merges; the `X.Y.Z` tag is
   then created on the resulting merge commit on `main`. Start from an up-to-date
   `main` (`git switch main && git pull`).
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

### 6. Commit the bump on a `release/X.Y.Z` branch and open a PR

`main` is protected (ruleset "main"), so the bump cannot be pushed to `main`
directly. Branch, commit, and open a PR. Stage only the bump + tracker/doc files.
Single-line subject, project style, **no** `Co-Authored-By`, no emojis:

```bash
git switch -c release/X.Y.Z
git commit -m "Release X.Y.Z: <one-line summary of what this release ships>"
git push -u origin release/X.Y.Z
gh pr create --base main --title "Release X.Y.Z: <summary>" --body "<summary>"
```

### 7. Hand off the merge, then tag the merged `main` (the tag push is the publish trigger)

The merge is a **human gate** the ruleset enforces — do not merge the PR yourself:

- The PR needs **one approving review** and **last-push approval** (don't push more
  commits after it's approved, or it needs re-approval).
- It must be **merged with a merge commit** (`allowed_merge_methods: ["merge"]` —
  squash/rebase are disabled).

Once the maintainer has merged the PR, fast-forward local `main` and tag the merge
commit (bare tag, no `v` prefix), then push the tag:

```bash
git switch main && git pull --ff-only
python scripts/check_release_version.py --ref refs/tags/X.Y.Z  # re-confirm on merged main
git tag -a X.Y.Z -m "Release X.Y.Z - <summary>"
git push origin X.Y.Z
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
- Delete the merged `release/X.Y.Z` branch (`git push origin --delete release/X.Y.Z`).
- State the published version, the PyPI URL, and what the next milestone/release is
  (from Current Status -> Next).

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
  bump straight to `main`, and never self-approve/merge — the review + merge is a
  human gate. The `X.Y.Z` tag is created on the merged `main` afterwards.
- **`1.0.0` is a sign-off, not a default.** Get explicit user confirmation against
  the stability gate; never tag it autonomously.
- **Stop on the first failure** — dirty tree, red gate, guard mismatch, tag
  conflict, unmerged/unapproved PR, failed workflow. Surface it and wait.
- **No `Co-Authored-By`, no emojis** (project rules).

---

## When NOT to use this skill

- Just bumping the version without releasing — do that one edit, don't tag.
- Mid-milestone, or before the milestone's work is committed and the gates are green.
- A docs-only or tracker-only change — edit directly; a release is a tag + publish.
