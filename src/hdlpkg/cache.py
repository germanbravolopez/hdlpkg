"""Content-addressed local cache.

The cache is the local, on-disk store the packager populates while resolving cores,
so repeated builds are offline and reproducible. It is **content-addressed**: a
blob is keyed by the SHA-256 digest of its own bytes, which makes storage
deduplicated, immutable, and tamper-evident.

The defining property is **verify-on-read**: :meth:`ContentAddressedCache.get`
recomputes the digest of what it reads and refuses to return it if it disagrees
with the requested key, so a corrupted or tampered blob fails closed rather than
poisoning a build. Writes are atomic (temp file + ``os.replace``) so a crash mid
-write never leaves a half-written blob under a valid-looking key.

Blobs are sharded git-style (``<root>/sha256/ab/cdef...``) to keep directories
small. The digest format is the canonical ``sha256:<hex>`` produced by
:func:`hdlpkg.lockfile.sha256_digest`. This is the store the registry
backends (M4) fetch into; what a "core blob" contains is defined by packaging (M5).
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from pathlib import Path

from .exceptions import RegistryError
from .lockfile import sha256_digest

__all__ = ["DEFAULT_CACHE_DIRNAME", "ContentAddressedCache", "default_cache_root"]

DEFAULT_CACHE_DIRNAME = ".hdlpkg"
_SHA256_HEX_LEN = 64
_HEX = set(string.hexdigits)


def default_cache_root() -> Path:
    """The default user-level cache directory (enables cross-project offline reuse)."""
    return Path.home() / DEFAULT_CACHE_DIRNAME / "cache"


def _split_digest(digest: str) -> tuple[str, str]:
    """Validate and split a ``sha256:<hex>`` digest; raise on a malformed one."""
    algorithm, separator, hexdigest = digest.partition(":")
    if (
        separator != ":"
        or algorithm != "sha256"
        or len(hexdigest) != _SHA256_HEX_LEN
        or any(char not in _HEX for char in hexdigest)
    ):
        raise RegistryError(f"Not a valid sha256 digest: {digest!r}")
    return algorithm, hexdigest


@dataclass(frozen=True)
class ContentAddressedCache:
    """A SHA-256 content-addressed blob store rooted at a directory."""

    root: Path

    def path_for(self, digest: str) -> Path:
        """The on-disk path a blob with *digest* is (or would be) stored at."""
        algorithm, hexdigest = _split_digest(digest)
        return self.root / algorithm / hexdigest[:2] / hexdigest[2:]

    def has(self, digest: str) -> bool:
        """True if a blob with *digest* is present in the cache."""
        return self.path_for(digest).is_file()

    def put(self, data: bytes) -> str:
        """Store *data*, returning its ``sha256:<hex>`` digest (idempotent)."""
        digest = sha256_digest(data)
        path = self.path_for(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.parent / (path.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)  # atomic publish into the store
        return digest

    def get(self, digest: str) -> bytes:
        """Return the blob for *digest*, verifying integrity on the way out.

        Raises :class:`RegistryError` if the blob is absent or its content no
        longer digests to *digest* (corruption/tampering -> fail closed).
        """
        path = self.path_for(digest)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise RegistryError(f"{digest} is not in the cache ({self.root}): {exc}") from exc
        actual = sha256_digest(data)
        if actual != digest:
            raise RegistryError(
                f"Cache integrity check failed for {digest}: stored content digests to {actual}."
            )
        return data
