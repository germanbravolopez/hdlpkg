# Example IP cores

Real, self-contained IP cores with valid `ip.toml` manifests. They exist to:

- give the docs concrete cores to point at instead of inline snippets, and
- drive the packager's integration tests against genuine manifests on disk
  (parsing, validation, fileset/file consistency, and the dependency graph).

These are reference manifests, not a verified HDL library — the SystemVerilog is
intentionally small and the testbenches are smoke tests, not full verification.

## Cores

| Core | VLNV | Depends on | What it is |
|------|------|-----------|------------|
| [fifo/](fifo/) | `acme:common:fifo:1.0.0` | — | Synchronous FWFT FIFO (configurable width/depth). |
| [uart/](uart/) | `acme:comm:uart:1.2.0` | `acme:common:fifo ^1.0.0` | 8N1 UART with a FIFO-buffered receive path. |

The UART depends on the FIFO, so together they form a minimal two-node dependency
graph that stays entirely within this directory — handy for exercising the
resolver (roadmap M1) once it lands.

## Layout

Each core is a directory with a manifest and its sources:

```
<core>/
  ip.toml          # the manifest (identity, filesets, targets, dependencies)
  rtl/*.sv         # synthesizable sources (the "rtl" fileset)
  tb/*.sv          # smoke testbench (the "tb" fileset)
```

## Try them

```bash
python -m hdlpkg info examples/fifo/ip.toml
python -m hdlpkg validate examples/uart/ip.toml
```

`tests/integration/test_examples.py` checks that every manifest here validates,
that every file each fileset lists exists on disk, and that every `acme`
dependency resolves to another example core in this tree.
