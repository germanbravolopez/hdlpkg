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
pip install hdl-ip-packager
hdlpkg --help            # if 'hdlpkg' is not on PATH: python -m hdl_ip_packager --help
```

> **Trying a pre-release (e.g. a `1.0.0-rc.N` candidate)?** `pip` skips pre-releases by
> default, so ask for it explicitly:
> ```bash
> pip install --pre hdl-ip-packager        # newest, including pre-releases
> pip install hdl-ip-packager==1.0.0rc1    # or pin the exact candidate
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
| **Fileset** | A named group of source files of one HDL type (e.g. `rtl`, `tb`). |
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
hdlpkg export-ipxact examples/uart/ip.toml          # IEEE 1685 XML
hdlpkg pack examples/uart/ip.toml --sbom --search examples   # .ipkg + CycloneDX SBOM
```

## Authoring your own core

```bash
mkdir my_uart && cd my_uart
hdlpkg init --vendor mycorp --library comm --name uart
```

This writes a valid starter `ip.toml` (one `rtl` fileset, one `sim` target) that
passes `validate` immediately. Then:

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

## Sharing over a registry (local, HTTP, or OCI)

The `--registry` flag takes a **location**, not just a directory. The same
publish/consume commands work against three backends, chosen by the location string:

| Location | Backend |
|----------|---------|
| a path, e.g. `./registry` | a local directory registry |
| `https://ip.corp.local/acme` | an HTTP registry (any `GET`/`PUT`-capable server) |
| `oci://harbor.corp.local/ip` | an **OCI** registry (Harbor, Artifactory, Nexus, GitLab, Zot, ECR/ACR) — `oci+http://` for a plaintext/dev one |

Network registries are **private by default**: you authenticate once with `hdlpkg
login`, and `resolve` / `install` / `publish` then use the stored credential
automatically. Nothing is exposed publicly — the registry is whatever server you point
at (typically one your company self-hosts).

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

To try this end to end without standing up a server, a no-auth [Zot](https://zotregistry.dev)
binary or `docker run -d -p 5000:5000 registry:2` gives you a real OCI registry on
`oci+http://127.0.0.1:5000/ip` in one command.

## Typical workflows

- **Consume a dependency**: declare it (`hdlpkg add`) → `resolve` (writes `ip.lock`)
  → `install` (fetch + verify into the cache) → `gen <target>` to build.
- **Reproducible / CI builds**: commit `ip.lock`, then build with `install --locked`
  and `gen --locked <target>` — these use the *exact* pinned versions and never
  re-resolve, so the build is byte-for-byte the same everywhere. `hdlpkg resolve`
  is the one command that updates the lock to newer compatible versions.
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
- [Architecture](architecture.md) — how the pieces fit and why.
- [Progress tracker](progress_tracker.md) — what is implemented, what is planned.
