# IP-XACT export — `ipxact.py`

Export a manifest as an IEEE 1685 (IP-XACT) component XML, so a core authored with
this packager can be consumed by the wider EDA tool ecosystem (Vivado in particular).
Pure module.

- **Source**: [src/hdl_ip_packager/ipxact.py](../../src/hdl_ip_packager/ipxact.py)
- **Import**: `from hdl_ip_packager import to_ipxact, IPXACT_NAMESPACE`

## Purpose

IP-XACT is the XML standard for *describing* an IP component — its VLNV identity, its
source filesets, and a model of build views. We already borrow its VLNV scheme (see
[identity](identity.md)); this module emits a full component document.

Conveniently, the manifest fileset `type` vocabulary
(`systemVerilogSource` / `verilogSource` / `vhdlSource`) **is** the IP-XACT `fileType`
vocabulary, so it passes straight through.

## API

```python
def to_ipxact(manifest: Manifest) -> str       # deterministic XML string
IPXACT_NAMESPACE                                # the 1685-2014 schema namespace
```

`to_ipxact` is pure (no I/O) and deterministic — same manifest, byte-identical XML.

## What it produces

A 1685-2014 `ipxact:component` with, in schema order:

- the **VLNV** (`vendor` / `library` / `name` / `version`);
- a **`model`** with one `view` + `componentInstantiation` per `[targets.*]` (carrying
  the target's `moduleName` and `fileSetRef`s);
- the **`fileSets`** — each file with its `fileType`;
- the package `description`.

Built with the stdlib `xml.etree.ElementTree` (namespaced, indented), so it has no
third-party dependency. The output is well-formed and structurally conventional;
validating it against the official Accellera XSD is a tracked follow-up.

## Example

```python
from hdl_ip_packager import Manifest, to_ipxact

xml = to_ipxact(Manifest.from_path("examples/uart/ip.toml"))
assert xml.startswith('<?xml version="1.0"')
# <ipxact:component> with vendor/library/name/version, a sim+synth model, fileSets…
```

`hdlpkg export-ipxact` writes this to a file; see [the CLI page](cli.md).
