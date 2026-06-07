# CLI (`hdlpkg`) — command reference

The command-line interface. It is intentionally thin: it parses arguments and
delegates to the library, so every behavior stays unit-testable. Run it as the
`hdlpkg` console script or as `python -m hdl_ip_packager`.

- **Source**: [src/hdl_ip_packager/cli.py](../../src/hdl_ip_packager/cli.py)

## Conventions

- **Invocation**: `hdlpkg <command> [args]`. `hdlpkg --version` prints `hdlpkg X.Y.Z`;
  `hdlpkg --help` (or no command) prints usage.
- **Exit codes**: `0` success; `1` a packager error (printed as `error: <message>` to
  stderr); `2` a planned-but-unimplemented command.
- `[path]` defaults to `./ip.toml`. `--search` is repeatable; when omitted it defaults
  to the manifest's parent directory.

## Authoring

### `info [path]`
Print the parsed identity, description, licence, dependencies, filesets, and targets
of a manifest.

### `validate [path]`
Parse and fully validate a manifest; print `OK: <vlnv> is a valid manifest.` (exit 0)
or the validation error (exit 1).

### `init [dir]`
Scaffold a starter `ip.toml` (one `rtl` fileset, one `sim` target) via
[`scaffold`](manifest.md#scaffolding-a-starter-manifest-scaffoldpy-behind-hdlpkg-init).
Flags: `--vendor`, `--library`, `--name`, `--version` (default `0.1.0`),
`--description`, `--license`, `--top`, `--force`. The three identity fields are
prompted for **only when stdin is a TTY** (so CI/tests never block); refuses to
overwrite an existing `ip.toml` unless `--force`.

## Resolve & fetch

### `resolve [path] [--search DIR …] [--output FILE]`
[Resolve](resolver.md) the dependency graph against a
[local-directory registry](registry.md) over the `--search` dirs and write a
deterministic [`ip.lock`](lockfile.md) (default next to the manifest). Prints the
chosen VLNVs.

### `install [path] [--search DIR …] [--cache-dir DIR] [--output FILE]`
Resolve **and fetch**: every pinned core is fetched into the
[content-addressed cache](cache.md) (`--cache-dir`, default `~/.hdlpkg/cache`), each
fetched digest is verified against the lockfile (**fails closed**), and the lockfile
is written.

### <a id="tree"></a>`tree [path] [--search DIR …]`
Resolve and **print the dependency graph** as an ASCII tree
([`treeview`](../../src/hdl_ip_packager/treeview.py)), annotating each edge with its
constraint and the chosen version; diamonds are expanded once and later marked `(*)`.

```
acme:comm:uart:1.2.0
└── acme:common:fifo ^1.0.0 -> 1.0.0
```

## Package, publish, distribute

### `pack [path] [--output FILE] [--sbom [FILE]] [--search DIR …]`
Build a deterministic [`.ipkg`](packaging.md) (default `<vlnv>.ipkg`) and print its
size + SHA-256. With `--sbom`, also write a [CycloneDX SBOM](sbom.md) (default
`<vlnv>.cdx.json`), resolving dependencies over `--search` so the SBOM pins concrete
versions.

### `publish [path] --registry DIR`
Pack the core and publish it into a writable [`LocalRegistry`](registry.md)
(**append-only** — re-publishing a version is refused).

### `pull <vlnv> --registry DIR [--output DIR] [--cache-dir DIR]`
Fetch a core by VLNV into the cache and print its digest; with `--output`, also
extract it (with path-traversal protection) into that directory.

### `yank <vlnv> --registry DIR`
Hide a published version from new resolves (a `.yanked` marker) without breaking
existing lockfiles.

## Generate tool/interop outputs

### `gen <target> [path] [--search DIR …] [--output DIR]`
Generate tool-flow inputs for a `[targets.<target>]` via the
[backends](backends.md): resolve dependencies, assemble the design, render, and write
the files into `--output` (default `gen/<target>/`). Tool flow is chosen by the
target's `toolflow` (`verilator`, `vivado`, `icarus`, `ghdl`, `yosys`).

### `export-ipxact [path] [--output FILE]`
Write an [IP-XACT](ipxact.md) (IEEE 1685-2014) component XML (default
`<vendor>.<library>.<name>.<version>.xml`).

## Planned

### `add <vlnv>` *(planned)*
Add a dependency to `ip.toml`. Currently reports "not implemented yet" and exits `2`.

## Example session

```bash
hdlpkg init --vendor acme --library comm --name uart   # scaffold ip.toml
hdlpkg validate ip.toml                                # check it
hdlpkg resolve ip.toml --search ../cores               # write ip.lock
hdlpkg tree ip.toml --search ../cores                  # inspect the graph
hdlpkg gen sim ip.toml --search ../cores               # Verilator inputs
hdlpkg pack ip.toml --sbom --search ../cores           # .ipkg + SBOM
hdlpkg publish ip.toml --registry ../registry          # share it
```
