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
  ([`_cmd_install`](../../src/hdlpkg/cli.py)). `resolve` = update the lock *without* fetching;
  `pull <vlnv> --output DIR` = extract **one** core's source tree to disk; `gen <target>` =
  emit ready-to-run tool inputs (extracting deps into `<cache>/src/<digest>/`).
- **The lockfile already records a per-package `source`** (a free-form string), set at resolve
  from `registry.source_for(vlnv)`: `path:…`, `registry:http://…`, `oci://…`, or
  `git+<url>@<sha>` ([lockfile.py](../../src/hdlpkg/lockfile.py),
  [`_build_lock`](../../src/hdlpkg/cli.py)). **So the lock is already heterogeneous-registry
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

1. `CompositeRegistry` + repeatable `--registry` across resolve/install/gen/tree (+ pull). Unit
   tests for union/precedence; a shadowed-VLNV warning.
2. `--locked` fetch from the lock's `source` (offline + multi-registry straight from the lock).
3. `hdlpkg install <vlnv>` one-shot (declare + resolve + lock + cache).
4. `vendor`/`sync` source materialization to a predictable tree (the Makefile case).
5. Docs + a `hdlpkg-livetest` scenario exercising heterogeneous registries (OCI + Git + local).

Parts A (1–2) and B (3–4) are independent; A can ship first.

## 8. Sequencing

**Open.** This work is customer-driven and touches the core consume flow every adopter uses.
Candidate: slot **Part A (multi-registry)** as the next release ahead of, or alongside, the
planned 0.15.0 IP-XACT ports work — to be decided with the maintainer. No version is committed
in this document yet.
