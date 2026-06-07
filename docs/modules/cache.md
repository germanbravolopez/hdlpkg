# Content-addressed cache — `cache.py`

The local, on-disk store the packager populates while resolving cores, so repeated
builds are offline and reproducible.

- **Source**: [src/hdl_ip_packager/cache.py](../../src/hdl_ip_packager/cache.py)
- **Import**: `from hdl_ip_packager import ContentAddressedCache, default_cache_root`

## Purpose & properties

A blob is keyed by the **SHA-256 of its own bytes**, which makes the store:

- **deduplicated** — identical content is stored once;
- **immutable** — a key always maps to the same bytes;
- **tamper-evident** — the key *is* the integrity check.

The defining behavior is **verify-on-read**: `get()` recomputes the digest of what it
reads and refuses to return it if it disagrees with the requested key, so a corrupted
or tampered blob **fails closed** rather than poisoning a build. Writes are **atomic**
(temp file + `os.replace`), so a crash mid-write never leaves a half-written blob
under a valid-looking key. Blobs are sharded git-style
(`<root>/sha256/ab/cdef…`) to keep directories small.

## API

`ContentAddressedCache` is a frozen dataclass over a `root: Path`.

| Member | Description |
|--------|-------------|
| `put(data: bytes) -> str` | Store bytes, return the `sha256:<hex>` digest. Idempotent. |
| `get(digest: str) -> bytes` | Return the blob, **verifying** on the way out. Raises `RegistryError` if absent or corrupt. |
| `has(digest: str) -> bool` | Is the blob present? |
| `path_for(digest: str) -> Path` | Where a blob is (or would be) stored. |

`default_cache_root() -> Path` returns the user-level cache dir
(`~/.hdlpkg/cache`), so cores are reused across projects. Digests must be the
canonical `sha256:<hex>` form ([`sha256_digest`](lockfile.md)); a malformed digest
raises `RegistryError`.

## Role in the system

[Registry](registry.md) backends `fetch` a core's [`.ipkg`](packaging.md) into this
cache; the [lockfile](lockfile.md) then `verify`s the fetched digests. `hdlpkg
install` and `hdlpkg pull` both populate it.

## Example

```python
from hdl_ip_packager import ContentAddressedCache, default_cache_root

cache = ContentAddressedCache(default_cache_root())
digest = cache.put(b"core bytes")
assert cache.has(digest)
assert cache.get(digest) == b"core bytes"   # verified on read
```
