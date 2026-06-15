"""Integration test for ``hdlpkg resolve`` end to end on the bundled examples.

The UART example depends on the FIFO example (`acme:common:fifo` ^1.0.0). Resolving
it against the `examples/` tree must discover the FIFO core, write a deterministic
`ip.lock`, and that lockfile must parse back and verify against the manifest digests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hdlpkg import cli
from hdlpkg.cache import ContentAddressedCache
from hdlpkg.lockfile import Lockfile, sha256_digest
from hdlpkg.registry import LocalDirectoryRegistry
from hdlpkg.vlnv import Vlnv

pytestmark = pytest.mark.integration

_REPO = Path(__file__).resolve().parents[2]
_EXAMPLES = _REPO / "examples"
_UART = _EXAMPLES / "uart" / "ip.toml"
_FIFO = _EXAMPLES / "fifo" / "ip.toml"


def test_resolve_writes_lockfile_for_examples(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "ip.lock"
    rc = cli.main(["resolve", str(_UART), "--search", str(_EXAMPLES), "--output", str(output)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "acme:common:fifo:1.0.0" in out

    lock = Lockfile.from_path(output)
    locked = {str(p.vlnv): p for p in lock.packages}
    assert "acme:common:fifo:1.0.0" in locked

    fifo = locked["acme:common:fifo:1.0.0"]
    assert fifo.source == "path:examples/fifo"
    # The recorded checksum is the packed .ipkg digest, and it self-verifies.
    assert fifo.checksum.startswith("sha256:")
    registry = LocalDirectoryRegistry([_EXAMPLES])
    assert fifo.checksum == sha256_digest(registry.artifact_bytes(Vlnv.parse(str(fifo.vlnv))))
    lock.verify({p.vlnv: p.checksum for p in lock.packages})


def test_install_fetches_into_cache(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    cache_dir = tmp_path / "cache"
    output = tmp_path / "ip.lock"
    rc = cli.main(
        [
            "install",
            str(_UART),
            "--search",
            str(_EXAMPLES),
            "--cache-dir",
            str(cache_dir),
            "--output",
            str(output),
        ]
    )
    assert rc == 0
    assert "Installed 1 package(s)" in capsys.readouterr().out

    # The fetched core is in the cache under its locked checksum, and verifies.
    lock = Lockfile.from_path(output)
    cache = ContentAddressedCache(cache_dir)
    for pkg in lock.packages:
        assert cache.has(pkg.checksum)
        assert sha256_digest(cache.get(pkg.checksum)) == pkg.checksum


def test_resolve_is_deterministic(tmp_path) -> None:
    # Running the command twice yields byte-identical lockfile text.
    first, second = tmp_path / "a.lock", tmp_path / "b.lock"
    for output in (first, second):
        argv = ["resolve", str(_UART), "--search", str(_EXAMPLES), "--output", str(output)]
        assert cli.main(argv) == 0
    assert first.read_bytes() == second.read_bytes()
