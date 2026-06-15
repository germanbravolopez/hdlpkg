# Name-mangling — `mangle.py`

Lets two versions of one **design unit** — a package, SV module/program, SV interface,
or VHDL entity — coexist in a single `gen` build by rewriting each version's unit name
to a unique one. Pure module (no I/O): it operates on source text passed in, so the file
work stays in the [CLI](cli.md). Full design rationale:
[docs/design/module-entity-coexistence.md](../design/module-entity-coexistence.md).

- **Source**: [src/hdlpkg/mangle.py](../../src/hdlpkg/mangle.py)
- **Import**: `from hdlpkg import rewrite_sv_packages, rewrite_vhdl_packages, declared_packages, mangled_name, plan_package_mangling`

## Why

The [resolver](resolver.md)'s `isolate_namespaces` policy keeps incompatible versions
of a package, but SystemVerilog puts every `package` name in **one global namespace**,
so two `package bus_pkg;` declarations collide at elaboration. Mangling renames each
version (`bus_pkg` → `bus_pkg_v1_1_0` / `bus_pkg_v2_0_0`) and rewrites every
consumer's references to the version *it resolved to*, so both build together. This is
the "physical" half of multi-version coexistence (the "bookkeeping" half is the
resolver/lock/tree).

## Safety: classify-all-or-refuse

A name is rewritten only in the declaration/reference positions its unit kind allows,
via per-language comment/string-aware scanners (no parser). For **packages** every
reference is keyword-marked (`::` / `use work.`), so the rewriter just touches those
positions. For **SV modules/interfaces** an instantiation has *no* leading keyword, so
mangling is **classify-all-or-refuse**: a version is renamed only when *every* occurrence
of its name is provably a declaration, an instantiation/reference, or inert — otherwise
the whole coexistence is refused (never a partial rewrite). A colliding module/interface/
entity name also declared by an *unrelated* core is refused (the name is ambiguous).

Positions handled per kind:

- **SV packages** — `package <n>` / `endpackage : <n>`, `import <n>::`, `<n>::`.
- **VHDL packages** (case-insensitive) — `package <n>` / `package body <n>`,
  `end [package [body]] <n>`, `use work.<n>`.
- **SV modules/programs** — `module`/`macromodule`/`program <n>`, `endmodule : <n>`, and
  instantiations `<n> [#(…)] <inst> […]* (` (parameter maps, instance arrays, multiple
  instances, generate-nested).
- **SV interfaces** — the above plus a port/variable type `<n> sig`, `virtual <n> v`, and
  a modport select `<n>.<modport>`.
- **VHDL entities** — `entity`/`architecture A of`/`component`/`end <n>` declarations,
  direct `entity work.<n>`, and component instantiation `label : [component] <n>`
  (generate-nested for both).

A coincidental signal named `bus_pkg`, or a name inside a comment/string, is **never**
touched. **Refused / not handled**: an unknown source language; a (System)Verilog macro
that *constructs* a name by token pasting; an SV interface in an unmodeled type context
(e.g. a type-parameter default); and a VHDL `use`/reference against a named library other
than `work` (everything is analyzed into `work`).

## API

| Function | Description |
|----------|-------------|
| `mangled_name(name, version) -> str` | `("bus_pkg", 1.1.0)` → `"bus_pkg_v1_1_0"` (HDL-safe). |
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
from hdlpkg import rewrite_sv_packages

src = "module fifo; import bus_pkg::*; logic [DATA_WIDTH-1:0] c; endmodule"
print(rewrite_sv_packages(src, {"bus_pkg": "bus_pkg_v1_1_0"}))
# module fifo; import bus_pkg_v1_1_0::*; logic [DATA_WIDTH-1:0] c; endmodule
```
