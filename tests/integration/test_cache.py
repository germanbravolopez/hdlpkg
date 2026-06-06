"""Tests for the content-addressed cache.

The cache touches the filesystem, so these are integration tests using ``tmp_path``
as the cache root. They cover the round-trip, content-addressing (idempotent puts,
deduplication), and the defining property: verify-on-read fails closed when a
stored blob is corrupted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hdl_ip_packager.cache import ContentAddressedCache, default_cache_root
from hdl_ip_packager.exceptions import RegistryError
from hdl_ip_packager.lockfile import sha256_digest

pytestmark = pytest.mark.integration


def test_put_then_get_round_trips(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    digest = cache.put(b"hello core")
    assert digest == sha256_digest(b"hello core")
    assert cache.get(digest) == b"hello core"


def test_has_reflects_presence(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    digest = sha256_digest(b"data")
    assert not cache.has(digest)
    cache.put(b"data")
    assert cache.has(digest)


def test_put_is_idempotent_and_content_addressed(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    first = cache.put(b"same bytes")
    second = cache.put(b"same bytes")
    assert first == second
    # Stored exactly once at the sharded path.
    assert cache.path_for(first).is_file()


def test_path_is_sharded(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    digest = cache.put(b"x")
    hexdigest = digest.split(":", 1)[1]
    expected = tmp_path / "sha256" / hexdigest[:2] / hexdigest[2:]
    assert cache.path_for(digest) == expected
    assert expected.is_file()


def test_get_missing_blob_raises(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    with pytest.raises(RegistryError, match="not in the cache"):
        cache.get(sha256_digest(b"absent"))


def test_verify_on_read_fails_closed_on_corruption(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path)
    digest = cache.put(b"trusted content")
    # Tamper with the stored blob behind the cache's back.
    cache.path_for(digest).write_bytes(b"evil content")
    with pytest.raises(RegistryError, match="integrity"):
        cache.get(digest)


@pytest.mark.parametrize(
    "bad",
    ["", "sha256:", "sha256:zz", "md5:" + "a" * 32, "a" * 64, "sha256:" + "a" * 63],
)
def test_invalid_digest_is_rejected(tmp_path: Path, bad: str) -> None:
    cache = ContentAddressedCache(tmp_path)
    with pytest.raises(RegistryError, match="valid sha256 digest"):
        cache.path_for(bad)


def test_default_cache_root_is_under_home() -> None:
    root = default_cache_root()
    assert root.name == "cache"
    assert Path.home() in root.parents
