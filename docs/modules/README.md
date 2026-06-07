# Module reference (user manual)

Per-module reference for the `hdl_ip_packager` library and the `hdlpkg` CLI. Each
page covers one module's purpose, public API, behavior, errors, and a worked example.
New to the tool? Start with the [User guide](../user_guide.md); for the design
rationale and how the modules fit together, see [architecture.md](../architecture.md).

The library is layered, with a **pure core** (parsing/logic, no I/O) and I/O only at
the edges (the CLI and registry/cache). The pages below follow that flow:

## Foundation (pure value types)

| Module | What it covers |
|--------|----------------|
| [Versioning](versioning.md) | `Version` + `VersionConstraint`: SemVer parsing, ordering, constraint matching |
| [Identity (VLNV)](identity.md) | `PackageRef` + `Vlnv`: how a core is named |
| [Manifest (`ip.toml`)](manifest.md) | The `Manifest` model + the `ip.toml` format, plus the `init` scaffolder |
| [Errors](exceptions.md) | The `HdlPackagerError` exception hierarchy |

## Resolve & record

| Module | What it covers |
|--------|----------------|
| [Resolver](resolver.md) | `resolve` → one concrete version per package (backtracking, newest-compatible) |
| [Lockfile (`ip.lock`)](lockfile.md) | Serialize/verify a resolution with per-core source + SHA-256 |

## Distribute

| Module | What it covers |
|--------|----------------|
| [Content-addressed cache](cache.md) | SHA-256-keyed local blob store with verify-on-read |
| [Registry](registry.md) | The `Registry` interface + local / HTTP / writable-local backends |
| [Packaging (`.ipkg`)](packaging.md) | The deterministic `.ipkg` artifact: build, extract, read |

## Generate & interop

| Module | What it covers |
|--------|----------------|
| [Tool-flow backends](backends.md) | EDAM intermediate → Verilator / Vivado / Icarus / GHDL / Yosys inputs |
| [IP-XACT export](ipxact.md) | IEEE 1685-2014 component XML |
| [SBOM (CycloneDX)](sbom.md) | Deterministic CycloneDX 1.5 bill of materials |

## Interface

| Module | What it covers |
|--------|----------------|
| [CLI (`hdlpkg`)](cli.md) | Full command reference for every `hdlpkg` subcommand |

> The public API is re-exported from the top-level package, so
> `from hdl_ip_packager import Manifest, resolve, pack_core, …` works directly.
