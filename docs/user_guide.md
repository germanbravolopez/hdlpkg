# User guide

A hands-on introduction to **HDL IP Packager** (`hdlpkg`) — what it is, what you can
do with it, and how to do it. For the per-module reference see the
[module manual](modules/README.md); for the design rationale see
[architecture.md](architecture.md).

## What is it?

`hdlpkg` is a **package and dependency manager for HDL IP cores** (Verilog, VHDL,
SystemVerilog) — think Cargo or npm, but for reusable hardware design blocks. You
describe a core once in a small `ip.toml` manifest; the tool then versions it,
resolves its dependencies to exact versions, fetches and verifies them, packages the
core for distribution, and generates the input files your simulator or synthesis tool
needs.

It exists because HDL reuse today is mostly manual (copy a folder, hope the versions
match). `hdlpkg` brings the software world's reproducibility — semantic versioning,
a committed lockfile, content-addressed integrity — to hardware.

## What you can achieve

- **Author & validate** a core with a clear, declarative manifest (`init`, `validate`,
  `info`).
- **Declare dependencies** on other cores by version *constraints* (`^1.2.0`) and
  **resolve** them to exact versions, recorded in a committed, verifiable `ip.lock`
  (`resolve`, `tree`). Compatible dependents unify to one version; an *incompatible*
  conflict is handled by a configurable policy (`[resolution] on-conflict` /
  `--on-conflict`). Versions may be SemVer or, for vendor IP, an `opaque` token.
- **Fetch & cache** dependencies into a content-addressed store that is offline,
  deduplicated, and tamper-evident (`install`).
- **Package & share** a core as a deterministic `.ipkg` and publish it — to a local
  directory, or a **private, self-hosted HTTP or OCI registry** (Harbor, Artifactory,
  Nexus, GitLab, Zot, ECR/ACR) your team runs on its own network — with append-only
  versions, `yank`, and `hdlpkg login` auth (`pack`, `publish`, `pull`, `yank`, `login`).
- **Generate tool inputs** for Verilator, Vivado, Icarus Verilog, GHDL, or Yosys from
  a single target definition (`gen`).
- **Interoperate**: export an IP-XACT (IEEE 1685) description for other tools, and
  emit a CycloneDX SBOM for supply-chain auditing (`export-ipxact`, `pack --sbom`).

## Install

Requires **Python 3.11+**. Install the published package from PyPI:

```bash
pip install hdlpkg
hdlpkg --help            # if 'hdlpkg' is not on PATH: python -m hdlpkg --help
```

> **Trying a pre-release (e.g. a `1.0.0-rc.N` candidate)?** `pip` skips pre-releases by
> default, so ask for it explicitly:
> ```bash
> pip install --pre hdlpkg        # newest, including pre-releases
> pip install hdlpkg==x.y.z       # or pin the exact candidate
> ```

From a source checkout instead (for development — tests, lint, types):

```bash
pip install -e ".[dev]"          # docs site extras: pip install -e ".[docs]"
```

## Concepts in 60 seconds

| Term | Meaning |
|------|---------|
| **VLNV** | A core's name: `vendor:library:name:version`, e.g. `acme:comm:uart:1.2.0`. |
| **`ip.toml`** | The manifest at a core's root: identity, dependencies, filesets, targets. |
| **Fileset** | A named group of source files of one HDL type (e.g. `rtl`, `tb`); entries may be literal paths, globs (`rtl/**/*.vhd`), or a directory. |
| **Target** | A build: which filesets feed which tool flow, and the top unit. |
| **Constraint** | A version range a dependency accepts: `^1.2.0`, `~1.2.0`, `>=1,<2` (or `=D5020100` for an opaque core). |
| **Version scheme** | `[package].scheme`: `semver` (default), `calver` (`2024.1`, year-as-major), `monotonic` (`r3`), or `opaque` (uninterpreted tokens, pinned exactly). |
| **Conflict policy** | `[resolution] on-conflict`: how an incompatible conflict is handled — `fail_on_conflict` (default), `use_latest`, or `isolate_namespaces`. |
| **`ip.lock`** | The generated, committed record pinning each dependency to one exact version + checksum. |
| **Registry** | Where cores live to be fetched/published: a local directory, or a network registry by URL — `http(s)://…` or an **OCI** registry `oci://…` (Harbor/Artifactory/Zot/GitLab/ECR), which can be private and self-hosted. |
| **Credentials** | A per-host token (or username+secret) for a private registry, stored by `hdlpkg login` and used automatically; a `docker login` is reused as a fallback. |
| **`.ipkg`** | The deterministic, content-addressed package file for one core. |

## A first walkthrough (using the bundled examples)

The repo ships two real cores under [`examples/`](../examples/): a FIFO
(`acme:common:fifo`) and a UART (`acme:comm:uart`) that depends on it. Run these from
the repo root.

**1. Inspect a core**

```bash
hdlpkg info examples/uart/ip.toml
hdlpkg validate examples/uart/ip.toml
```

**2. See its dependency graph**

```bash
hdlpkg tree examples/uart/ip.toml --search examples
# acme:comm:uart:1.2.0
# `-- acme:common:fifo ^1.0.0 -> 1.0.0
```

`--search examples` tells `hdlpkg` where to discover candidate cores.

**3. Resolve to a lockfile**

```bash
hdlpkg resolve examples/uart/ip.toml --search examples
# writes examples/uart/ip.lock pinning acme:common:fifo:1.0.0 + checksum
```

Commit `ip.lock` alongside your core — it makes every later build reproducible.

**4. Generate simulator / synthesis inputs**

```bash
hdlpkg gen sim   examples/uart/ip.toml --search examples --output build/sim
hdlpkg gen synth examples/uart/ip.toml --search examples --output build/synth
```

`gen sim` produces a Verilator `.vc` (the UART's `sim` target uses `verilator`);
`gen synth` produces a Vivado `.tcl`. The FIFO dependency's RTL is pulled in
automatically; its testbench is not. `gen` *generates the tool inputs* — to actually
compile/simulate/synthesize you run them with the EDA tool itself (Verilator, GHDL,
Vivado, …), which you install separately.

**5. Package, publish, and pull**

```bash
hdlpkg pack examples/fifo/ip.toml --output fifo.ipkg
hdlpkg publish examples/fifo/ip.toml --registry ./registry
hdlpkg pull acme:common:fifo:1.0.0 --registry ./registry --output ./fetched-fifo
```

**6. Interop & supply chain**

```bash
hdlpkg export-ipxact examples/uart/ip.toml             # IEEE 1685-2014 XML (default)
hdlpkg export-ipxact examples/uart/ip.toml --std 2022  # IEEE 1685-2022 XML
hdlpkg pack examples/uart/ip.toml --sbom --search examples   # .ipkg + CycloneDX SBOM
```

`export-ipxact` maps the VLNV, a build view per `[targets.*]`, and the filesets. To carry
component **parameters** into the IP-XACT, declare them in an optional `[ipxact.parameters]`
table (additive; older `hdlpkg` simply ignores it):

```toml
[ipxact.parameters]
WIDTH = 8                                       # scalar shorthand -> value "8"
DEPTH = { value = 16, description = "FIFO depth" }
```

## Authoring your own core

```bash
mkdir my_uart && cd my_uart
hdlpkg init --vendor mycorp --library comm --name uart
```

This writes a valid starter `ip.toml` (one `rtl` fileset, one `sim` target) that
passes `validate` immediately. A brand-new core defaults to SemVer `0.1.0`. If your
IP uses a vendor or date version code that is not SemVer (e.g. `D5020204`), pick a
scheme so `init` accepts it and records it in the manifest:

```bash
hdlpkg init --vendor mycorp --library comm --name uart \
  --version D5020204 --scheme opaque    # or 'monotonic' for ordered build numbers
```

`--scheme` is one of `semver` (default), `calver`, `monotonic`, or `opaque`; it sets
`[package].scheme` (see the version-scheme glossary entry above). Then:

1. Add your sources under `rtl/` and list them in `[filesets.rtl]`.
2. Declare dependencies under `[dependencies]` with version constraints — by hand,
   or with `hdlpkg add` (which preserves your formatting and re-validates):
   ```bash
   hdlpkg add mycorp:common:fifo@^1.0.0
   ```
   ```toml
   [dependencies]
   "mycorp:common:fifo" = "^1.0.0"
   ```
3. Define the targets you build (`[targets.sim]`, `[targets.synth]`, …), choosing a
   `toolflow` (`verilator`, `vivado`, `icarus`, `ghdl`, `yosys`).
4. `hdlpkg validate`, then `resolve`, `gen`, and `pack` as above.

See the [manifest reference](modules/manifest.md) for every field.

## Packaging a generated / script-driven IP

Some cores are not a fixed list of RTL: the deliverable is a **generator** — a
Vivado/Tcl script (`build.tcl`), an IP-XACT description, and a few hand-written
HDL files — and the *real* sources are produced by running that script inside the
consumer's own simulation/synthesis flow (often a Makefile that calls the script,
then points the build at the generated directory). You can package this kind of IP
without changing any of that: `hdlpkg` versions and distributes the **inputs**, and
your existing flow still does the generation, untouched.

The trick is to read `[filesets]` for what it is — a **manifest of files to ship**,
each tagged with a `type` — not as "the RTL `hdlpkg` will compile". Two facts make
this work:

- **`type` is free-form.** Only `hdlpkg`'s own `gen` backends interpret it; `validate`,
  `pack`, `publish`, `resolve`, `install`, and `pull` carry every file **verbatim**,
  preserving its path. So a `.tcl`, an IP-XACT `.xml`, a constraints file, or anything
  else rides along untouched — tag them with a descriptive type like `tclSource` or
  `user`.
- **`[targets]` is optional.** If your internal customers build with their own
  Makefile/Tcl flow, you do not need a `[targets]` block at all. `hdlpkg`'s role is to
  replace "a git submodule pinned at some ref" with a **versioned, checksummed,
  resolvable package** of the IP sources; the generation step stays exactly where it is.

A generator-style `ip.toml` then looks like:

```toml
[package]
vendor  = "mycorp"
library = "video"
name    = "scaler"
version = "1.2.0"
top     = "scaler_top"           # informational: the generated/BD top

[filesets.vhdl]                  # hand-written HDL that lives in the repo
files = ["src/scaler_pkg.vhd", "src/scaler_top.vhd"]
type  = "vhdlSource"

[filesets.ipxact]                # IP-XACT submodule description, carried as-is
files = ["ip/scaler.xml", "ip/sub/axi.xml"]
type  = "user"

[filesets.generator]             # the Vivado generator script(s)
files = ["build.tcl"]
type  = "tclSource"
```

Package the **inputs, not the generated outputs**: the Vivado block-design files do
not exist until `build.tcl` runs (and their exact list is dynamic), so they are not
something to enumerate here. The consumer runs `hdlpkg install`/`pull` to land this
source tree where the submodule used to sit, and their Makefile runs `build.tcl` →
moves the generated files → adds the path to the build, exactly as before. `hdlpkg`
gives them the *versioned, locked, integrity-checked* source; it does not run the
generator or interfere with their tool flow.

### Globs and directories in a fileset

For a large IP you do not have to list every file. A `files` entry may be:

- a **literal** path — `src/scaler_top.vhd`;
- a **glob** — any entry containing `*`, `?`, or `[`; `**` recurses, e.g.
  `rtl/**/*.vhd` or `ip/*.xml`. A glob matches files only;
- a **directory** — `ip` packs every file under `ip/`, recursively.

So the IP above can collapse to whole trees:

```toml
[filesets.vhdl]
files = ["src/**/*.vhd"]
type  = "vhdlSource"

[filesets.ipxact]
files = ["ip"]                   # the entire IP-XACT submodule tree
type  = "user"
```

Expansion happens at `pack`/`publish`/`gen` time, resolved against the core directory;
matches are sorted so the `.ipkg` stays byte-for-byte deterministic. A glob or directory
that matches **no** file is an error (a likely typo), and patterns may not escape the core
(`..` or absolute paths are rejected). The manifest still records the patterns you wrote,
so `ip.lock` and the SBOM are unaffected.

## Sharing over a registry (local, HTTP, or OCI)

The `--registry` flag takes a **location**, not just a directory. The same
publish/consume commands work against three backends, chosen by the location string:

| Location | Backend |
|----------|---------|
| a path, e.g. `./registry` | a local directory registry |
| `https://ip.corp.local/acme` | an HTTP registry (any `GET`/`PUT`-capable server) |
| `oci://harbor.corp.local/ip` | an **OCI** registry (Harbor, Artifactory, Nexus, GitLab, Zot, ECR/ACR) — `oci+http://` for a plaintext/dev one |
| `git+ssh://bitbucket.org/org/ip-registry.git` | a **Git** repository of cores (read-only); add `@<branch\|tag\|sha>` to pin a ref |

Network registries are **private by default**: you authenticate once with `hdlpkg
login`, and `resolve` / `install` / `publish` then use the stored credential
automatically. Nothing is exposed publicly — the registry is whatever server you point
at (typically one your company self-hosts). A **Git** registry instead uses your own git
credentials (ssh keys / credential helpers), and the lockfile records each core's exact
commit (`git+<url>@<sha>`) for traceability; it is read-only to the tool (consume with
`resolve` / `install` / `pull`, publish with the other backends).

### Publishing to a Git registry

A Git registry is **read-only to hdlpkg** — `hdlpkg publish --registry git+…` is not
supported. "Publishing" is just **git**: a Git registry is an ordinary repository holding
one directory per core, each with its `ip.toml` (and the files its `[filesets]` reference).
hdlpkg packs each core deterministically on the fly when a consumer fetches it, so the repo
stores **source**, not packed `.ipkg` blobs. Identity (the VLNV) comes from each manifest's
contents, not its path, so the folder layout is free (a `vendor/library/name/` convention is
just tidy):

```text
ip-registry.git/
  acme/common/fifo/1.0.0/    ip.toml (version = "1.0.0") + rtl/…
  acme/common/fifo/1.1.0/    ip.toml (version = "1.1.0") + rtl/…
```

To add a version, commit the core's directory and push (optionally tag the release):

```bash
git clone ssh://git@github.com/org/ip-registry.git && cd ip-registry
mkdir -p acme/common/fifo/1.1.0 && cp -r <fifo source>/* acme/common/fifo/1.1.0/
git add . && git commit -m "fifo 1.1.0" && git tag v1.1.0 && git push --follow-tags
```

**Branch / tag / commit pinning.** The cores do **not** have to live on `main`. Add
`@<ref>` to the location to consume from any ref — a branch (including a git-flow name with
a slash, e.g. `@feature/x` or `@release/1.0`), a tag, or a commit SHA:

```bash
hdlpkg resolve  my_soc/ip.toml --registry git+ssh://github.com/org/ip-registry.git@develop
hdlpkg install  my_soc/ip.toml --registry git+ssh://github.com/org/ip-registry.git@v1.1.0
```

With **no** `@<ref>`, the registry uses the remote's **default branch** (so a no-pin consume
needs the cores on that branch). A **tag wins over a same-named branch** (immutable
provenance), and `gen --locked` against a `@<sha>` pin works fully offline after the first
install. Since `GitRegistry` checks out **one ref** and scans that tree, every version you
want resolvable at a given ref must exist as its own directory there — or tag each release
and let consumers pin `@<tag>`. There is no `yank` on a Git registry: retract by pushing a
new commit/tag; anyone pinned to the old SHA still gets the old bits (by design).

**Producer — publish a core** (from the machine that has the source):

```bash
hdlpkg login   oci://harbor.corp.local/ip            # stores a per-host token
hdlpkg publish ip.toml --registry oci://harbor.corp.local/ip
```

For a registry that uses the OCI **token-exchange** (managed Harbor, a cloud registry),
log in with a username so the exchange (HTTP Basic -> short-lived token) is used:

```bash
hdlpkg login oci://harbor.corp.local/ip --username robot   # prompts for the password/robot token
```

A `docker login` you already did (`~/.docker/config.json`) is reused as a fallback, so
an already-authenticated registry may need no separate `hdlpkg login`.

**Consumer — resolve and build from the registry** (a different person, another machine):

```bash
hdlpkg login   oci://harbor.corp.local/ip            # once, if the registry is private
hdlpkg resolve my_soc/ip.toml --registry oci://harbor.corp.local/ip   # writes ip.lock
hdlpkg install my_soc/ip.toml --registry oci://harbor.corp.local/ip --locked
hdlpkg pull    acme:common:fifo:1.0.0 --registry oci://harbor.corp.local/ip --output ./fifo
```

`hdlpkg logout <location>` removes a stored credential. Publishing is **append-only**: a
version can never be overwritten (use a new version, or `yank` to retire a bad one).

**Adding a dependency in one command.** `install` also accepts dependency specs, so you can
declare and install in a single step — the `pip install <name>` shape — instead of editing
`ip.toml` (or running `hdlpkg add`) first:

```bash
hdlpkg install acme:common:fifo@^1.0.0 --registry oci://harbor.corp.local/ip
```

Each `vendor:library:name[@constraint]` argument is written into the manifest's
`[dependencies]`, then the usual resolve + lock + cache runs. You can name the manifest too
(`hdlpkg install my_soc/ip.toml acme:common:fifo`); with no path it defaults to `./ip.toml`,
and several specs may be added at once. Building (`hdlpkg gen`) stays a separate step.
(Adding deps re-resolves, so it cannot be combined with `--locked`.)

To try this end to end without standing up a server, a no-auth [Zot](https://zotregistry.dev)
binary or `docker run -d -p 5000:5000 registry:2` gives you a real OCI registry on
`oci+http://127.0.0.1:5000/ip` in one command.

### Resolving across more than one registry

A project's dependencies may not all live in the same place — one core in your company's
OCI registry, another in a Git repository. Pass `--registry` **more than once** and the
locations form an ordered **search path** (the order on the command line is the
precedence). It works on `resolve`, `install`, `gen`, `tree`, and `pull`:

```bash
hdlpkg install my_soc/ip.toml \
  --registry oci://harbor.corp.local/ip \
  --registry git+ssh://bitbucket.org/org/ip-registry.git
```

- The set of available versions is the **union** across all reachable registries, so the
  resolver sees every version regardless of which registry hosts it.
- Each resolved core is fetched from the **first** registry, in order, that offers it, and
  the lockfile records that registry as the core's `source` — so a resolve spanning several
  registries pins each core to its true origin with no lockfile-format change.
- If the **same** version of a core is offered by more than one registry, the first wins and
  a warning notes the others (the lockfile's checksum still fails closed if a later fetch
  returns different bytes). An **unreachable** registry is skipped with a warning and the
  resolve continues from the rest.

Credentials stay per-host (via `hdlpkg login`), so each registry in the path authenticates
with its own stored credential.

**Vendoring sources for a Makefile.** The cache holds packed `.ipkg` blobs, not loose
source, so a plain Makefile cannot read a dependency from it. `hdlpkg vendor` extracts every
locked dependency into a predictable tree — `<DIR>/<vendor>/<library>/<name>/`, the
`node_modules` of HDL — so an existing Makefile can just include the files:

```bash
hdlpkg vendor                       # writes ./deps/<vendor>/<library>/<name>/ for each locked core
hdlpkg vendor --output third_party  # or choose the directory
```

It needs an `ip.lock` (run `resolve`/`install` first) and, like `--locked`, fetches each core
from the source the lock recorded (pass `--registry` to override). Re-running replaces each
core's tree so the vendored copy always matches the lock. Building (`hdlpkg gen`) remains
independent — use `vendor` when you drive the build yourself, `gen` when you want hdlpkg to
emit the tool inputs.

**Installing straight from the lock.** Once `ip.lock` is written, each package entry records
the exact registry it came from (its `source`). So `install --locked` and `gen --locked` with
**no** `--registry`/`--search` fetch each core from its own recorded source — a lock that
spans several registries reinstalls with no flags at all:

```bash
hdlpkg install my_soc/ip.toml --locked   # fetches each core from the source ip.lock recorded
```

Passing `--registry`/`--search` still overrides (it fetches everything from there instead). A
core already in the local cache is reused untouched, so a repeat `--locked` install/gen is
fully offline. (A recorded OCI source assumes HTTPS; for a plaintext `oci+http://` dev
registry, pass `--registry` explicitly.)

### Pointing at a managed registry (JFrog Artifactory, Nexus, cloud)

`hdlpkg`'s OCI backend speaks the standard OCI distribution API, so any registry that
hosts **Docker/OCI** repositories works as a shared registry — JFrog Artifactory, Sonatype
Nexus, GitLab, ECR/ACR, and so on. The rule of thumb: **whatever base you use for
`docker login` / `docker push` to that repository, put `oci://` in front of it and append a
namespace segment for your cores.**

For **JFrog Artifactory**, the location is:

```
oci://<artifactory-host>/<docker-repo-key>/ip
```

- `<artifactory-host>` — the Docker registry domain. On JFrog SaaS that is
  `your-org.jfrog.io`; on a self-hosted instance it is whatever your reverse proxy serves
  to `docker` (the subdomain `repo.artifactory.corp` or the path
  `artifactory.corp/artifactory/api/docker/<repo>` form) — use exactly what `docker push`
  already uses.
- `<docker-repo-key>` — an Artifactory repository whose **package type is Docker/OCI**:
  a *local* repo to publish into (with deploy permission), or a *virtual* repo to consume
  from.
- `ip` — a sub-namespace `hdlpkg` stores cores under; pick one and keep it consistent.

Artifactory issues short-lived tokens after Basic auth (the OCI **token-exchange**), so log
in with `--username`, using an Artifactory **identity token / API key** as the password
(not your UI password):

```bash
# Producer -- deploy into a local Docker repo
hdlpkg login   oci://your-org.jfrog.io/ip-docker-local/ip --username robot-ci
hdlpkg publish ip.toml --registry oci://your-org.jfrog.io/ip-docker-local/ip

# Consumer -- read from a virtual Docker repo
hdlpkg login   oci://your-org.jfrog.io/ip-docker/ip --username robot-dev
hdlpkg resolve my_soc/ip.toml --registry oci://your-org.jfrog.io/ip-docker/ip
hdlpkg install my_soc/ip.toml --registry oci://your-org.jfrog.io/ip-docker/ip --locked
```

Use the **same full location** for `login` and `--registry` (the stored credential is keyed
by host, so they must match). A `docker login` you already did is reused from
`~/.docker/config.json`, so an already-authenticated host may need no separate `hdlpkg
login`.

Two gotchas: the repository must be **Docker/OCI** package type (a generic Artifactory repo
has no `/v2/` endpoint and will 404), and a `publish` `401` is almost always a
permissions / identity-token problem rather than a `hdlpkg` one — confirm `docker push` to
the same base works first; if Docker works, `hdlpkg` will.

## Typical workflows

- **Consume a dependency**: declare it (`hdlpkg add`) → `resolve` (writes `ip.lock`)
  → `install` (fetch + verify into the cache) → `gen <target>` to build.
- **Reproducible / CI builds**: commit `ip.lock`, then build with `install --locked`
  and `gen --locked <target>` — these use the *exact* pinned versions and never
  re-resolve, so the build is byte-for-byte the same everywhere. After
  `install --locked` populates the cache, `gen --locked` builds **fully offline** —
  no `--search` or `--registry` needed, since dependencies are materialized from the
  cache by their lockfile digest. `hdlpkg resolve` is the one command that updates the
  lock to newer compatible versions.
- **Build straight from a registry**: `gen <target> --registry <location>` fetches each
  dependency's `.ipkg` into the cache and uses it — so you can generate against published
  cores without checking out their source trees.
- **Publish a core**: `validate` → `pack` → `publish --registry …` (append-only;
  `yank` to retire a bad version).
- **Consume from a published registry**: `resolve`/`install`/`tree --registry <dir>`
  resolve and fetch directly from a registry you (or someone else) published to —
  not just `pull` by exact VLNV.
- **Hand off to a vendor tool**: `gen <target>` for the simulator/synth inputs, or
  `export-ipxact` for an IP-XACT description.

## Where to go next

- [Module manual](modules/README.md) — the full per-module / per-command reference.
- [CLI reference](modules/cli.md) — every command, flag, and exit code.
- **Man page** — `man ./man/hdlpkg.1` (or install it so `man hdlpkg` works; see
  [`man/README.md`](../man/README.md)).
- [Architecture](architecture.md) — how the pieces fit and why.
- [Progress tracker](progress_tracker.md) — what is implemented, what is planned.
