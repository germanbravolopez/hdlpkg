"""End-to-end lifecycle: the full producer -> consumer round trip via the real CLI.

Where the other integration modules each pin down one command, this one drives the
*whole* distribution story as a black box, exactly as an external user (and the
``hdlpkg-consumer-demo`` project) would:

    publish (fifo, uart)  ->  resolve --registry  ->  tree  ->  gen --locked
                          ->  install --locked     ->  pull --output

It asserts the properties that matter across the chain: the dependency unifies to
the published version, the lockfile records a ``registry:`` source, ``--locked``
generation is reproducible and pulls the dependency in, the cache fills, and a
``pull`` re-extracts a usable source tree. Everything runs against the bundled
``examples/`` cores in a temp registry/cache, so it needs no external repo.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hdl_ip_packager import cli
from hdl_ip_packager.lockfile import Lockfile

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def consumer(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Publish fifo + uart to a temp registry; return (registry, cache, uart_manifest).

    The returned manifest is a standalone copy of the UART core (``acme:comm:uart``,
    which depends on ``acme:common:fifo ^1.0.0``) so resolves write the lockfile next
    to it without touching the checked-in example.
    """
    registry = tmp_path / "registry"
    for core in ("fifo", "uart"):
        rc = cli.main(["publish", str(EXAMPLES / core / "ip.toml"), "--registry", str(registry)])
        assert rc == 0, f"publish {core} failed"

    manifest = tmp_path / "consumer" / "ip.toml"
    manifest.parent.mkdir(parents=True)
    shutil.copy(EXAMPLES / "uart" / "ip.toml", manifest)
    return registry, tmp_path / "cache", manifest


def test_full_lifecycle_publish_resolve_gen_install_pull(
    consumer: tuple[Path, Path, Path], tmp_path: Path, capsys
) -> None:
    registry, cache, manifest = consumer

    # 1. resolve straight from the published registry -> a lockfile pinned to it.
    assert cli.main(["resolve", str(manifest), "--registry", str(registry)]) == 0
    lock = Lockfile.from_path(manifest.parent / "ip.lock")
    fifo = next(p for p in lock.packages if p.vlnv.name == "fifo")
    assert str(fifo.vlnv) == "acme:common:fifo:1.0.0"
    assert fifo.source.startswith("registry:")
    capsys.readouterr()

    # 2. tree reflects the resolved dependency.
    assert cli.main(["tree", str(manifest), "--registry", str(registry)]) == 0
    assert "acme:common:fifo" in capsys.readouterr().out

    # 3. gen --locked is reproducible and pulls the locked dependency into the output.
    #    gen still needs loose sources, so it scans examples/ (the lockfile pins versions).
    out = tmp_path / "gen"
    rc = cli.main(
        ["gen", "sim", str(manifest), "--search", str(EXAMPLES), "--output", str(out), "--locked"]
    )
    assert rc == 0
    vc = (out / "uart.vc").read_text(encoding="utf-8")
    assert "sync_fifo.sv" in vc  # the locked FIFO dependency was generated in
    capsys.readouterr()

    # 4. install --locked fills the content-addressed cache from the lockfile.
    rc = cli.main(
        [
            "install",
            str(manifest),
            "--registry",
            str(registry),
            "--cache-dir",
            str(cache),
            "--locked",
        ]
    )
    assert rc == 0
    out_install = capsys.readouterr().out
    assert "locked package(s)" in out_install
    assert "acme:common:fifo:1.0.0" in out_install
    assert any(cache.rglob("*")), "cache should be populated after install"

    # 5. pull the dependency back out by VLNV and extract a usable source tree.
    extracted = tmp_path / "pulled"
    rc = cli.main(
        [
            "pull",
            "acme:common:fifo:1.0.0",
            "--registry",
            str(registry),
            "--cache-dir",
            str(cache),
            "--output",
            str(extracted),
        ]
    )
    assert rc == 0
    assert next(extracted.rglob("sync_fifo.sv"), None) is not None
    assert next(extracted.rglob("ip.toml"), None) is not None


def test_gen_locked_is_byte_for_byte_reproducible(
    consumer: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    """Two ``gen --locked`` runs off the same lockfile produce identical output."""
    registry, _cache, manifest = consumer
    assert cli.main(["resolve", str(manifest), "--registry", str(registry)]) == 0

    def gen(into: Path) -> str:
        assert (
            cli.main(
                [
                    "gen",
                    "sim",
                    str(manifest),
                    "--search",
                    str(EXAMPLES),
                    "--output",
                    str(into),
                    "--locked",
                ]
            )
            == 0
        )
        return (into / "uart.vc").read_text(encoding="utf-8")

    assert gen(tmp_path / "a") == gen(tmp_path / "b")
