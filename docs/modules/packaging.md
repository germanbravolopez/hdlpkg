# Packaging (`.ipkg`) — `packaging.py`

Build and read the distributable `.ipkg` artifact — the single-file form of an IP
core used for distribution.

- **Source**: [src/hdl_ip_packager/packaging.py](../../src/hdl_ip_packager/packaging.py)
- **Import**: `from hdl_ip_packager import pack_core, extract_ipkg, manifest_from_ipkg, artifact_filename`

## What an `.ipkg` is

A gzip-compressed tar holding the core's `ip.toml` plus **every file its filesets
declare**. It is built **deterministically**:

- entries sorted by name,
- fixed mode (`0644`), owner/group zeroed,
- zero mtime, and a zeroed gzip header timestamp.

So the same core always packs to **byte-identical** bytes, which makes its SHA-256 a
stable **content address**. The `.ipkg` is the unit the [registry](registry.md)
serves, the [cache](cache.md) stores, and the [lockfile](lockfile.md) pins — the cache
key and lockfile checksum are the packed-content digest.

## API

| Function | Description |
|----------|-------------|
| `pack_core(manifest, core_dir) -> bytes` | Read the manifest + every fileset file under `core_dir` and return deterministic `.ipkg` bytes. |
| `extract_ipkg(data, dest) -> Path` | Unpack into `dest`, **rejecting unsafe paths** (absolute, `..`, or non-regular members). Returns `dest`. |
| `manifest_from_ipkg(data) -> Manifest` | Parse just the `ip.toml` carried inside an `.ipkg`. |
| `artifact_filename(vlnv) -> str` | The conventional `vendor-library-name-version.ipkg` name. |

## Safety

`extract_ipkg` validates every member before extracting: it refuses paths that are
absolute, contain `..`, or are not regular files/dirs — so a malicious archive cannot
write outside the destination (path-traversal protection).

`pack_core` also rejects fileset paths that **escape the core directory** (absolute
paths or `..`), so a manifest cannot pack a file from outside its own tree.

## Errors

`PackagingError` — a missing fileset file or a path escaping the core while packing,
a corrupt archive, or an unsafe member while extracting.

## Example

```python
from hdl_ip_packager import Manifest, pack_core, manifest_from_ipkg, sha256_digest

m = Manifest.from_path("examples/fifo/ip.toml")
data = pack_core(m, "examples/fifo")
assert pack_core(m, "examples/fifo") == data        # deterministic
assert sha256_digest(data).startswith("sha256:")    # stable content address
assert manifest_from_ipkg(data).vlnv == m.vlnv
```

`hdlpkg pack` writes the `.ipkg` (and optionally a [SBOM](sbom.md)); `hdlpkg pull`
fetches and can extract it. See [the CLI page](cli.md).
