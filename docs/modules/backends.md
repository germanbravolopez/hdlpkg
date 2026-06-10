# Tool-flow backends — `backends/`

Turn a resolved design into the concrete input files an EDA tool consumes, behind
`hdlpkg gen`. Tool specifics never leak into the manifest/resolver/packaging layers.

- **Source**: [src/hdl_ip_packager/backends/](../../src/hdl_ip_packager/backends/)
- **Import**: `from hdl_ip_packager import build_eda_design, get_backend, supported_toolflows, CoreSource, EdaDesign, EdaFile`

## The pipeline

```
resolved design ──▶ build_eda_design() ──▶ EdaDesign ──▶ Backend.generate() ──▶ {filename: text}
 (root + deps)        (edam.py, pure)      (tool-agnostic)   (per tool, pure)        (CLI writes)
```

Everything here is **pure**: `build_eda_design` only joins paths and re-orders
metadata, and a backend's `generate` returns a `{filename: text}` mapping and writes
nothing — the [CLI](cli.md) does the file writing.

## The EDAM-like intermediate (`edam.py`)

`build_eda_design(root, target, dependencies)` flattens a design into an ordered list
of source files with a top unit and a tool flow.

- **`CoreSource`** — `manifest: Manifest` + `root: str` (the core's on-disk dir,
  treated as an opaque string and only joined with fileset paths).
- **`EdaFile`** — `path`, `file_type` (normalized: `systemVerilog` / `verilog` /
  `vhdl`), `core` (owning VLNV).
- **`EdaDesign`** — `name`, `toplevel`, `toolflow`, `files: tuple[EdaFile, ...]`,
  `parameters`.

### Fileset selection rules

- The **root** contributes the filesets its chosen `[targets.<target>]` lists — so a
  `sim` target keeps its testbench, a `synth` target does not.
- Each **dependency** contributes only its synthesizable surface: its `rtl` fileset
  if present, otherwise every fileset whose name is not a known testbench name. A
  dependency's testbench is never compiled into a dependent.
- **`Fileset.depend` is honored**: any selected fileset also pulls in the filesets it
  declares it depends on (transitively, emitted before it, de-duplicated, cycle-safe)
  — so a core states exactly what a fileset needs rather than relying on naming.
- Cores are emitted **dependencies-first** via a topological sort (ties by VLNV);
  duplicate file paths are de-duplicated.

An unknown target name raises `ValueError`. If the dependencies contain **two versions
of one package** (possible under the resolver's `isolate_namespaces`
[conflict policy](resolver.md)), `build_eda_design` raises `BackendError` unless
`allow_multiversion=True`. The CLI's `gen` sets that flag only **after**
[name-mangling](mangle.md) the coexisting SystemVerilog/VHDL packages, so the colliding
names no longer clash; a conflict the mangler cannot handle (two *module*/interface or
*entity* versions, or an unknown language) still gets a clear `BackendError`.

## Backends and the registry

`get_backend(toolflow) -> Backend` returns the backend for a `[targets.*].toolflow`
value; `supported_toolflows()` lists them. An unknown tool flow raises `BackendError`.
Every backend uses shared `Backend` guards — `_reject_unsupported` (a file type it
cannot handle) and `_require_top` (a missing top, or a `top` that is not a safe HDL
identifier, since the top is interpolated into generated scripts) — each raising
`BackendError`.

| `toolflow` | Backend | Emits | Notes |
|------------|---------|-------|-------|
| `verilator` | `VerilatorBackend` | `<name>.vc` | Verilator command file (`--top-module` + sources). Rejects VHDL. |
| `vivado` | `VivadoBackend` | `<name>.tcl` | `read_verilog -sv`/`read_verilog`/`read_vhdl`, `set_property top`, `update_compile_order`. |
| `icarus` | `IcarusBackend` | `<name>.cmd` + `run_iverilog.sh` | Icarus Verilog command file + run script. Rejects VHDL. |
| `ghdl` | `GhdlBackend` | `run_ghdl.sh` | GHDL analyze/elaborate/run. **VHDL only.** |
| `yosys` | `YosysBackend` | `<name>.ys` | Yosys synthesis script. Verilog/SV only (VHDL needs the ghdl-yosys plugin). |

Adding a backend is one class implementing `Backend.generate` plus an entry in the
`backends` registry — no change to the manifest, resolver, or CLI.

## Errors

`BackendError` (unknown tool flow, unsupported file type, missing top); `ValueError`
for an unknown target name.

## Example

```python
from hdl_ip_packager import Manifest, build_eda_design, get_backend, CoreSource

root = CoreSource(Manifest.from_path("examples/uart/ip.toml"), "examples/uart")
fifo = CoreSource(Manifest.from_path("examples/fifo/ip.toml"), "examples/fifo")
design = build_eda_design(root, "sim", [fifo])
files = get_backend(design.toolflow).generate(design)
print(files["uart.vc"])      # --top-module uart_tb + the ordered sources
```
