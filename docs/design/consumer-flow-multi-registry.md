# Design proposal — consumer flow: multi-registry resolve + install ergonomics

**Status:** **proposed / under discussion.** Decisions in [§5](#5-decisions-so-far-firm) are
firm; a lot is still open ([§6](#6-open-questions--still-negotiable)). **Target:** TBD — Part A
(multi-registry) is a strong candidate to slot ahead of the planned 0.15.0 IP-XACT ports work
([0.15.0-ipxact-ports-businterfaces.md](0.15.0-ipxact-ports-businterfaces.md)); sequencing is
itself an open question ([§8](#8-sequencing)).

Captures a design conversation driven by a real adopter evaluating the **consumer** side.

---

## 1. Motivation (from a real adopter)

Two questions from a customer integrating IP at the SoC level:

- **Q1 — multiple registries.** An SoC declares ~4 dependencies. They are easy to *identify*
  by VLNV, but what if they live in **different registries** — one in JFrog Artifactory (OCI),
  another in a Git repo? The customer suggested baking the registry into the dependency path
  (docker-compose / image-ref style); we prefer **registries supplied on the command**, not
  per-VLNV.
- **Q2 — one command.** Why several commands to consume an IP (resolve → install → pull),
  versus `pip install <name>`? And — once source isn't necessarily "pulled" — **how does a
  Makefile-based consumer get the source on disk** if the cache only holds the `.ipkg`?

## 2. Current behavior (grounding — what ships today in 0.14.0)

- **`--registry` is single-valued** per command (not repeatable).
- **`install` is already a one-shot:** `hdlpkg install <manifest> --registry …` does **resolve
  + write `ip.lock` + fetch the `.ipkg` into the content-addressed cache** in one command
  ([`_cmd_install`](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/cli.py)). `resolve` = update the lock *without* fetching;
  `pull <vlnv> --output DIR` = extract **one** core's source tree to disk; `gen <target>` =
  emit ready-to-run tool inputs (extracting deps into `<cache>/src/<digest>/`).
- **The lockfile already records a per-package `source`** (a free-form string), set at resolve
  from `registry.source_for(vlnv)`: `path:…`, `registry:http://…`, `oci://…`, or
  `git+<url>@<sha>` ([lockfile.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/lockfile.py),
  [`_build_lock`](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/cli.py)). **So the lock is already heterogeneous-registry
  capable** — only the single `--registry` on the CLI limits it. No lock-format change is
  needed for multi-registry.

## 3. Part A — multi-registry resolve

### 3a. Rejected: registry baked into the VLNV (docker-compose style)

A VLNV is the core's **identity**; it must mean the same thing wherever the core is hosted.
Putting the registry in the dependency path couples identity to location and breaks down:
re-hosting or mirroring an IP would force edits to every consumer's `ip.toml`; a diamond
dependency on the same core reached via two registries becomes two "different" packages; and
per-dependency infra/credentials leak into the manifest. Cargo, npm, and pip all keep the
package **name** pure and treat registries/indexes as **configuration**. **Firm rejection.**

### 3b. Proposed: an ordered search path via repeatable `--registry` + a `CompositeRegistry`

- Make `--registry` **repeatable**; CLI order = precedence.
- A small **`CompositeRegistry`** (implements the existing `Registry` interface) aggregates the
  backends: `versions(ref)` returns the **union** across all registries (the resolver sees
  every available version); `manifest` / `artifact_bytes` / `source_for(vlnv)` delegate to the
  **first registry in order** that has that exact VLNV.
- `source_for` therefore returns the *actual* registry used, recorded in the lock — so a
  resolve spanning JFrog + Git + a local path pins each core to its true origin, no format
  change. **Checksums catch content divergence**: if the same exact VLNV exists in two
  registries with different bytes, first-wins pins one digest and any later fetch of different
  bytes fails `lock.verify`. Add a **warning** when a VLNV is shadowed (found in >1 registry
  with differing digests) so it is visible.

### 3c. Bonus: lock-driven `--locked` fetch

Because the lock stores each package's `source`, `install --locked` / `gen --locked` could
dispatch each package through `registry_from_location(pkg.source)` and fetch it **from its own
recorded registry** — multi-registry "just works" from the lock with **zero `--registry`
flags**, and stays reproducible. (Today `--locked` re-uses the single `--registry` passed.)

## 4. Part B — consumer flow ergonomics

### 4a. `install` is already the single consumer command

The perceived "many commands" is largely a docs/mental-model gap: the normal consume flow is
**`install`** (resolve + lock + fetch) then **`gen`** (build). `resolve` (lock-only) and `pull`
(extract one core) are specialized. Keeping resolve/`--locked` split is deliberate — it is what
makes builds reproducible (the opposite of pip conflating everything).

### 4b. A pip-like declare-and-install one-shot

Today declaring + installing a new dep is `hdlpkg add <vlnv>` then `hdlpkg install`. Propose a
one-shot **`hdlpkg install <vlnv> [<vlnv>…]`** that adds the dep(s) to `ip.toml`, resolves,
locks, and caches — the real `pip install <name>` experience. Build (`gen`) stays separate.

### 4c. The Makefile reuse gap — vendor source to a predictable tree

The content-addressed cache holds **`.ipkg` blobs, not loose source**, so a Makefile cannot read
it directly. To feed a Makefile the source must be **extracted to disk**. Today that is
`pull <vlnv> --output DIR` per dependency (the "replace the submodule" flow), or `gen` for the
built-in toolflows (which extracts into `<cache>/src/<digest>/`, an internal path). **`install`
alone is not enough for a Makefile consumer.** Propose an install-and-**vendor** capability — a
`hdlpkg vendor`/`sync` command, or `install --vendor DIR` — that extracts **all locked deps**
into a predictable layout (e.g. `deps/<vendor>/<name>/`), the `node_modules` of HDL, so existing
Makefiles can include them.

### 4d. Encrypted IP is forward-compatible

Extraction still lays files down even for encrypted IP — they are just **encrypted envelopes**
(IEEE 1735 `pragma protect`); the source is physically present for the tool to include and the
**EDA tool decrypts at compile time**. The cache/lock pin the *ciphertext* digest. So "vendor to
a directory → your Makefile builds" holds; the bytes are simply opaque to humans. ("Not
readable" ≠ "not on disk.")

## 5. Decisions so far (firm)

1. **VLNV stays location-independent** — reject registry-in-the-VLNV.
2. **Multiple registries are a CLI/config search path**, ordered, not per-dependency.
3. **No lock-format change** for multi-registry — the per-package `source` already exists.
4. **`gen` (build) stays a separate, deliberate step** from `install` (fetch).

## 6. Open questions / still negotiable

- **Duplicate-VLNV precedence.** First-in-order wins + warning (proposed) — *or* hard-error when
  the same exact VLNV appears in >1 registry, forcing the user to disambiguate? Error-mode is
  safer but noisier.
- **Version union vs registry pinning.** Should `versions(ref)` union across all registries
  (proposed, maximizes availability) — or, once a package is first seen in registry N, should
  *all* its versions come from N (avoids mixing sibling versions across registries)?
- **Where registries are declared.** CLI-only (`--registry …`), or also a project/workspace
  config (e.g. a `[registries]` list or a separate, possibly gitignored config file)? A
  per-project list is convenient but re-introduces some config; it must not become per-dep.
- **`--locked` source precedence.** Should `--locked` fetch from the lock's recorded `source`
  (ignoring `--registry`), from `--registry`, or let `--registry` override? Changing the
  current default (re-use `--registry`) has compatibility implications.
- **Unreachable registry during resolve.** Fall through to the next registry silently, warn, or
  fail? Affects the reproducibility / offline guarantees.
- **One-shot command surface.** Overload `install <vlnv>` vs a new flag vs `add --install`. If
  `install` accepts both a manifest path *and* VLNVs, resolve the ambiguity.
- **Vendoring shape.** New `vendor`/`sync` command vs `install --vendor DIR`? Layout
  (`deps/<vendor>/<name>/` vs include the version/library)? Opt-in vs default? How it coexists
  with `gen`'s own `<cache>/src/<digest>/` extraction (avoid two source copies).
- **Default consumer posture.** node_modules-style (vendor by default) vs Go-modules-style
  (build from cache, vendor on request)? This shapes how strong the "one command" story is.
- **Credentials across many registries.** Already per-host via the credential store; confirm no
  need for per-registry inline tokens.
- **Resolver semantics unchanged.** Confirm multi-registry does not alter unification/conflict
  policy — it only widens the candidate set.

## 7. Phasing (tentative)

1. **[done — `feature/multi-registry`]** `CompositeRegistry` + repeatable `--registry` across
   resolve/install/gen/tree/pull. The CLI order is the precedence; `versions` unions across all
   reachable backends and `manifest`/`artifact_bytes`/`source_for` (and the inherited `fetch`)
   delegate to the first backend that has the exact VLNV (so the lock pins each core's true
   origin — no lock-format change). A shadowed VLNV warns and takes the first; an unreachable
   backend is skipped with a warning. Decisions taken with the maintainer: **first-wins +
   warn** on duplicate VLNV, **union** versions across registries, **warn + continue** on an
   unreachable registry. Implemented in `registry.py` (`CompositeRegistry`,
   `composite_registry_from_locations`, `_registry_label`) and `cli.py` (repeatable
   `--registry`, `_selected_registries`, `_print_registry_warnings`); covered by
   `tests/unit/test_composite_registry.py` and `tests/integration/test_multi_registry_cli.py`,
   documented in the user guide. **Caveat:** a backend whose `versions()` swallows transport
   errors and returns `[]` (e.g. `HttpRegistry`) cannot be distinguished from "unknown
   package", so the unreachable-warning fires only when a backend actually raises — acceptable
   for now, revisit if it bites.
2. **[done — `feature/multi-registry`]** `--locked` fetch from the lock's `source` (offline +
   multi-registry straight from the lock). When `install --locked` / `gen --locked` is run with
   no `--registry`/`--search`, each package is fetched from the exact `source` its lock entry
   recorded, via a new `LockSourceRegistry` that dispatches each VLNV through
   `registry_from_lock_source` (which maps the recorded `path:` / `registry:` / `oci:` /
   `git+…@sha` forms back to a backend). An explicit `--registry`/`--search` still overrides
   (prior behavior). **Decision taken** for the §6 open question: `--locked` defaults to the
   lock's recorded source, and `--registry` overrides it — backward compatible (explicit flags
   behave as before) while making the no-flag case "install from the lock". **Caveat:** the
   recorded OCI `source` does not encode the transport scheme, so it is rebuilt as HTTPS; a
   plaintext `oci+http://` registry must be reached with an explicit `--registry`. Implemented
   in `registry.py` (`registry_from_lock_source`, `LockSourceRegistry`) and `cli.py`
   (`_locked_registry`); covered by `tests/unit/test_lock_source_registry.py` and
   `tests/integration/test_locked_from_lock_source_cli.py`; documented in the user guide.
3. **[done — `feature/multi-registry`]** `hdlpkg install <vlnv>` one-shot (declare + resolve +
   lock + cache). `install`'s positional became `nargs="*"`: a `vendor:library:name[@constraint]`
   token is added to the manifest's `[dependencies]` (reusing `editing.add_dependency`), then the
   normal resolve/lock/cache runs; a non-spec token is the manifest path (default `ip.toml`,
   at most one), and several specs may be added at once. **Decision** for the §6 "command
   surface" open question: **overload `install`** (not a new flag / `add --install`), with
   spec-vs-path disambiguation by whether the token parses as a `PackageRef`. Adding deps
   re-resolves, so it is refused with `--locked`; a self-dependency and two manifest paths are
   refused too. Implemented in `cli.py` (`_install_targets`, `_add_dependencies`,
   `_parse_dependency_spec`/`_looks_like_dependency_spec` factored out of `_cmd_add`); covered by
   `tests/integration/test_install_oneshot_cli.py`; man page regenerated; documented in the user
   guide. Build (`gen`) stays a separate, deliberate step (firm decision §5.4).
4. **[done — `feature/multi-registry`]** `vendor` source materialization to a predictable tree
   (the Makefile case). A new `hdlpkg vendor [path]` command reads the lock, fetches each core
   (reusing `_locked_registry`, so it works from the recorded source / cache, offline), verifies
   the digests against the lock (fail closed), and extracts each into
   `<DIR>/<vendor>/<library>/<name>/` (default `./deps`), clearing any stale tree first so the
   vendored copy matches the lock. **Decisions** for the §6 "vendoring shape" open question: a
   **new `vendor` command** (not `install --vendor`), layout **`<vendor>/<library>/<name>/`**
   (include library — VLNV identity is vendor:library:name — but not the version, so a Makefile
   include path is stable across version bumps), **opt-in** (run it explicitly; the default
   posture stays Go-modules-style "build from cache, vendor on request", not node_modules-style
   vendor-by-default). It coexists with `gen`'s own `<cache>/src/<digest>/` extraction rather
   than replacing it — `vendor` is for consumers driving their own Makefile, `gen` for the
   built-in toolflows. Implemented in `cli.py` (`_cmd_vendor`); covered by
   `tests/integration/test_vendor_cli.py`; man page regenerated; documented in the user guide.
5. **[done — `feature/multi-registry`]** Docs + a `hdlpkg-livetest` scenario exercising
   heterogeneous registries. The user guide gained sections for the multi-registry search path,
   installing straight from the lock, the `install <vlnv>` one-shot, and `hdlpkg vendor`;
   `vendor` is listed in the README and `architecture.md` command tables. `hdlpkg-livetest`
   gained a `--multi-registry` mode (`run_livetest.py:test_multi_registry`) that drives all four
   phases end to end through the real CLI against two local-directory registries — union
   resolve, first-wins shadow + warning, `--locked` fetch from the recorded source, `vendor`,
   and `install <vlnv>` — needing no server, Docker, or network (passes locally).

Parts A (1–2) and B (3–4) are independent; A can ship first. **All five phases are now
implemented on `feature/multi-registry`.**

## 8. Sequencing

**Resolved in implementation:** all five phases landed together on `feature/multi-registry`
(no `ip.toml`/`ip.lock` format change; the CLI surface grew the repeatable `--registry`, the
`install <vlnv>` overload, and the new `vendor` command). What remains is a maintainer call on
**which `0.x` release carries it** (a candidate to slot as `0.15.0` ahead of, or alongside, the
IP-XACT ports work) and merging `feature/multi-registry` -> `develop`.

The original open question follows.

**Open.** This work is customer-driven and touches the core consume flow every adopter uses.
Candidate: slot **Part A (multi-registry)** as the next release ahead of, or alongside, the
planned 0.15.0 IP-XACT ports work — to be decided with the maintainer. No version is committed
in this document yet.
