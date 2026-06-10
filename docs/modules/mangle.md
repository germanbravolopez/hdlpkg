# Name-mangling — `mangle.py`

Lets two versions of one **package** (SystemVerilog or VHDL) coexist in a single `gen`
build by rewriting each version's package name to a unique one. Pure module (no I/O):
it operates on source text passed in, so the file work stays in the [CLI](cli.md).

- **Source**: [src/hdl_ip_packager/mangle.py](../../src/hdl_ip_packager/mangle.py)
- **Import**: `from hdl_ip_packager import rewrite_sv_packages, rewrite_vhdl_packages, declared_packages, mangled_name, plan_package_mangling`

## Why

The [resolver](resolver.md)'s `isolate_namespaces` policy keeps incompatible versions
of a package, but SystemVerilog puts every `package` name in **one global namespace**,
so two `package bus_pkg;` declarations collide at elaboration. Mangling renames each
version (`bus_pkg` → `bus_pkg__v1_1_0` / `bus_pkg__v2_0_0`) and rewrites every
consumer's references to the version *it resolved to*, so both build together. This is
the "physical" half of multi-version coexistence (the "bookkeeping" half is the
resolver/lock/tree).

## Safety: only unambiguous package positions

A name is rewritten **only** where the HDL syntax makes it unambiguously a package
reference, so no parser is needed. Each language has its own comment/string-aware
scanner:

- **`rewrite_sv_packages`** (SystemVerilog) — `package <name>` / `endpackage : <name>`
  declarations, `import <name>::…`, and `<name>::…` scoped references; skips `//`,
  `/* */`, and `"…"`.
- **`rewrite_vhdl_packages`** (VHDL, case-insensitive) — `package <name>` /
  `package body <name>` declarations, `end [package [body]] <name>` labels, and
  `use work.<name>…` references; skips `--`, `/* */`, strings, and character literals.

A coincidental signal named `bus_pkg`, or the name inside a comment or string, is
**never** touched.

**Not handled** (refused upstream with a clear `BackendError`): two versions of a
*module*/interface (SV) or *entity* (VHDL) — instantiation position is ambiguous
without a real parser — and an unknown source language. **Known limitations**: an SV
macro that *constructs* a package name by token pasting, and a VHDL `use` against a
named library other than `work` (everything is analyzed into `work`), are left
untouched.

## API

| Function | Description |
|----------|-------------|
| `mangled_name(name, version) -> str` | `("bus_pkg", 1.1.0)` → `"bus_pkg__v1_1_0"` (HDL-safe). |
| `declared_packages` / `declared_vhdl_packages` | The package names declared in an SV / VHDL source. |
| `declared_modules` / `declared_vhdl_entities` | The SV module/interface / VHDL entity names (refusal check). |
| `rewrite_sv_packages` / `rewrite_vhdl_packages` | Rewrite package declarations + references per *renames* (VHDL keys are lowercased). |
| `plan_package_mangling(cores) -> ManglePlan` | Plan the renames for a set of `GenCore`s; raises `BackendError` for an unsupported conflict. |

`GenSourceFile` carries a `language` (the fileset kind); `GenCore` (a manifest + its
already-read sources) and `ManglePlan` (the `rewritten` text per source key + a
`renamed` report) are the planner's value types.
The [CLI](cli.md) `gen` reads the sources, calls the planner, writes the rewritten
tree into `<output>/src/`, and builds the design over it
([`build_eda_design(allow_multiversion=True)`](backends.md)).

## Example

```python
from hdl_ip_packager import rewrite_sv_packages

src = "module fifo; import bus_pkg::*; logic [DATA_WIDTH-1:0] c; endmodule"
print(rewrite_sv_packages(src, {"bus_pkg": "bus_pkg__v1_1_0"}))
# module fifo; import bus_pkg__v1_1_0::*; logic [DATA_WIDTH-1:0] c; endmodule
```
