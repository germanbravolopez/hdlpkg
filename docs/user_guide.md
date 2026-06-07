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
  **resolve** them to one exact version each, recorded in a committed, verifiable
  `ip.lock` (`resolve`, `tree`).
- **Fetch & cache** dependencies into a content-addressed store that is offline,
  deduplicated, and tamper-evident (`install`).
- **Package & share** a core as a deterministic `.ipkg` and publish it to a registry,
  with append-only versions and `yank` (`pack`, `publish`, `pull`, `yank`).
- **Generate tool inputs** for Verilator, Vivado, Icarus Verilog, GHDL, or Yosys from
  a single target definition (`gen`).
- **Interoperate**: export an IP-XACT (IEEE 1685) description for other tools, and
  emit a CycloneDX SBOM for supply-chain auditing (`export-ipxact`, `pack --sbom`).

## Install

Requires **Python 3.11+**. From the repo root:

```bash
python -m pip install -e .
hdlpkg --help            # or: python -m hdl_ip_packager --help
```

(For development — tests, lint, types — install the extras: `pip install -e ".[dev]"`.
For the docs site: `pip install -e ".[docs]"`.)

## Concepts in 60 seconds

| Term | Meaning |
|------|---------|
| **VLNV** | A core's name: `vendor:library:name:version`, e.g. `acme:comm:uart:1.2.0`. |
| **`ip.toml`** | The manifest at a core's root: identity, dependencies, filesets, targets. |
| **Fileset** | A named group of source files of one HDL type (e.g. `rtl`, `tb`). |
| **Target** | A build: which filesets feed which tool flow, and the top unit. |
| **Constraint** | A version range a dependency accepts: `^1.2.0`, `~1.2.0`, `>=1,<2`. |
| **`ip.lock`** | The generated, committed record pinning each dependency to one exact version + checksum. |
| **Registry** | Where cores live to be fetched/published (a local dir, an HTTP index, …). |
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
automatically; its testbench is not.

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
