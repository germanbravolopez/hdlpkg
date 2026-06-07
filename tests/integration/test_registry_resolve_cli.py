"""Integration test: resolve/install directly from a PUBLISHED registry (`--registry`)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hdl_ip_packager import cli
from hdl_ip_packager.lockfile import Lockfile

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def published(tmp_path: Path) -> tuple[Path, Path]:
    """Publish the FIFO core to a registry; return (registry_dir, uart_manifest)."""
    registry = tmp_path / "registry"
    assert (
        cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", str(registry)]) == 0
    )
    manifest = tmp_path / "ip.toml"
    shutil.copy(EXAMPLES / "uart" / "ip.toml", manifest)  # depends on acme:common:fifo ^1.0.0
    return registry, manifest


def test_resolve_from_published_registry(published: tuple[Path, Path]) -> None:
    registry, manifest = published
    assert cli.main(["resolve", str(manifest), "--registry", str(registry)]) == 0
    lock = Lockfile.from_path(manifest.parent / "ip.lock")
    pkg = next(p for p in lock.packages if p.vlnv.name == "fifo")
    assert str(pkg.vlnv) == "acme:common:fifo:1.0.0"
    assert pkg.source.startswith("registry:")  # came from the published registry


def test_install_locked_from_published_registry(published: tuple[Path, Path], tmp_path) -> None:
    registry, manifest = published
    assert cli.main(["resolve", str(manifest), "--registry", str(registry)]) == 0
    rc = cli.main(
        [
            "install",
            str(manifest),
            "--registry",
            str(registry),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--locked",
        ]
    )
    assert rc == 0


def test_tree_from_published_registry(published: tuple[Path, Path], capsys) -> None:
    registry, manifest = published
    assert cli.main(["tree", str(manifest), "--registry", str(registry)]) == 0
    assert "acme:common:fifo" in capsys.readouterr().out
