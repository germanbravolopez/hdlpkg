# Manifest (`ip.toml`) — `manifest.py` + `scaffold.py`

The IP core manifest: identity, dependencies, source filesets, and build targets.
The analogue of `Cargo.toml` / `package.json` / a FuseSoC `.core` file. Pure module
(parsing uses the stdlib `tomllib`, no third-party TOML dependency).

- **Source**: [src/hdl_ip_packager/manifest.py](../../src/hdl_ip_packager/manifest.py),
  [src/hdl_ip_packager/scaffold.py](../../src/hdl_ip_packager/scaffold.py)
- **Import**: `from hdl_ip_packager import Manifest, Dependency, Fileset, Target`

## The `ip.toml` format

Every core carries an `ip.toml` at its root:

```toml
schema      = 1                 # optional ip.toml format version (default 1)

[package]
vendor      = "acme"            # required ─┐
library     = "comm"            # required  ├ VLNV identity
name        = "uart"            # required  │
version     = "1.2.0"           # required ─┘ (SemVer)
description = "AXI-Lite UART"
license     = "Apache-2.0"      # SPDX id
authors     = ["Jane Doe <jane@acme.com>"]
top         = "uart_top"        # default top-level unit
keywords    = ["uart", "axi"]

[dependencies]
# "vendor:library:name" = "<constraint>"
"acme:common:fifo" = "^1.0.0"

[filesets.rtl]
files = ["rtl/uart_top.sv", "rtl/uart_rx.sv"]
type  = "systemVerilogSource"   # IP-XACT fileType vocabulary

[filesets.tb]
files  = ["tb/uart_tb.sv"]
type   = "systemVerilogSource"
depend = ["rtl"]                # other filesets this one needs

[targets.sim]
toolflow = "verilator"          # which backend (see backends.md)
filesets = ["rtl", "tb"]        # must reference defined filesets
top      = "uart_tb"            # overrides package.top for this target
```

Only `[package]` (with the four identity keys) is required; everything else is
optional. Unknown fields are ignored. The keys map onto the dataclasses below.

## Data model

`Manifest` is a frozen dataclass with these fields:

| Field | Type | Notes |
|-------|------|-------|
| `vlnv` | [`Vlnv`](identity.md) | parsed from the four identity keys |
| `description`, `license` | `str` | metadata |
| `authors`, `keywords` | `tuple[str, ...]` | |
| `top` | `str \| None` | default top unit |
| `dependencies` | `tuple[Dependency, ...]` | |
| `filesets` | `dict[str, Fileset]` | keyed by fileset name |
| `targets` | `dict[str, Target]` | keyed by target name |
| `schema_version` | `int` | the `ip.toml` format version (`MANIFEST_SCHEMA_VERSION`, default `1`) |
| `ref` (property) | [`PackageRef`](identity.md) | version-less key |

The optional top-level `schema` key declares the `ip.toml` format version (default
`1`). A manifest written for a **newer** schema than this `hdlpkg` understands is
rejected with a clear `ManifestError` rather than mis-parsed — the migration path the
format needs once it freezes at 1.0.

Supporting value types:

- **`Dependency`** — `ref: PackageRef` + `constraint: VersionConstraint`. `str(dep)`
  renders `"vendor:library:name = <constraint>"`.
- **`Fileset`** — `name`, `files: tuple[str, ...]`, `type: str`
  (default `"systemVerilogSource"`), `depend: tuple[str, ...]` (other filesets it
  pulls in — honored by tool-flow generation, see [backends](backends.md)).
- **`Target`** — `name`, `toolflow: str`, `filesets: tuple[str, ...]`,
  `top: str | None`.

## Loading & validation

| Constructor | Description |
|-------------|-------------|
| `Manifest.from_str(text) -> Manifest` | Parse from a TOML string. |
| `Manifest.from_path(path) -> Manifest` | Parse from an `ip.toml` file. |
| `Manifest.from_dict(data) -> Manifest` | Validate an already-parsed mapping. |

Validation is strict and the error message always names the offending field:

- `[package]` must exist and carry `vendor`/`library`/`name`/`version`; the version
  must be valid SemVer and the segments valid VLNV parts.
- Each dependency key must parse as a `PackageRef` and its value as a
  `VersionConstraint`.
- Each fileset must have a `files` list of strings.
- Each target must have a `toolflow`, and **every fileset it references must be
  defined** — a dangling reference is rejected with the list of known filesets.

All failures raise `ManifestError` (see [exceptions](exceptions.md)).

## Scaffolding a starter manifest (`scaffold.py`, behind `hdlpkg init`)

`scaffold.py` renders a fresh, valid `ip.toml` from a few fields. It is pure (no
I/O); the [CLI](cli.md) layer owns prompting and writing.

- **`ScaffoldOptions`** — a frozen value type with `vendor`/`library`/`name`
  (validated as VLNV segments), `version: Version`, optional `description`/`license`/
  `top` (defaults to the core name). Build from strings with
  `ScaffoldOptions.create(...)` (parses the version; default `0.1.0`). Properties:
  `effective_top`, `vlnv`.
- **`render_manifest(options) -> str`** — emits a complete manifest with one `rtl`
  fileset and one `sim` (Verilator) target. The output round-trips through
  `Manifest`, so a freshly scaffolded core passes `hdlpkg validate` immediately.

## Example

```python
from hdl_ip_packager import Manifest
from hdl_ip_packager.scaffold import ScaffoldOptions, render_manifest

text = render_manifest(ScaffoldOptions.create("acme", "comm", "uart"))
m = Manifest.from_str(text)
assert str(m.vlnv) == "acme:comm:uart:0.1.0"
assert "rtl" in m.filesets and "sim" in m.targets
```
