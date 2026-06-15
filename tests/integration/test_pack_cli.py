"""Integration tests for the pack / publish / pull / yank CLI commands.

These exercise the full distribution loop against a local registry directory:
pack a core to an .ipkg, publish it (append-only), pull it back into the cache and
extract it, and yank it so it disappears from new resolves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hdlpkg import cli
from hdlpkg.packaging import manifest_from_ipkg
from hdlpkg.registry import LocalRegistry
from hdlpkg.vlnv import PackageRef, Vlnv

pytestmark = pytest.mark.integration

_MANIFEST = '[package]\nvendor = "acme"\nlibrary = "common"\nname = "fifo"\nversion = "1.0.0"\n'


def _core(tmp_path: Path) -> Path:
    core = tmp_path / "fifo"
    core.mkdir()
    (core / "ip.toml").write_text(_MANIFEST, encoding="utf-8")
    return core


def test_pack_writes_ipkg(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    core = _core(tmp_path)
    out = tmp_path / "fifo.ipkg"
    rc = cli.main(["pack", str(core / "ip.toml"), "--output", str(out)])
    assert rc == 0
    assert "Packed acme:common:fifo:1.0.0" in capsys.readouterr().out
    assert manifest_from_ipkg(out.read_bytes()).vlnv == Vlnv.parse("acme:common:fifo:1.0.0")


def test_publish_is_append_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    core = _core(tmp_path)
    registry = tmp_path / "registry"
    argv = ["publish", str(core / "ip.toml"), "--registry", str(registry)]
    assert cli.main(argv) == 0
    assert "Published acme:common:fifo:1.0.0" in capsys.readouterr().out
    # Re-publishing the same version is refused.
    assert cli.main(argv) == 1
    assert "append-only" in capsys.readouterr().err


def test_pull_fetches_and_extracts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    core = _core(tmp_path)
    registry = tmp_path / "registry"
    cache = tmp_path / "cache"
    out = tmp_path / "pulled"
    assert cli.main(["publish", str(core / "ip.toml"), "--registry", str(registry)]) == 0
    rc = cli.main(
        [
            "pull",
            "acme:common:fifo:1.0.0",
            "--registry",
            str(registry),
            "--cache-dir",
            str(cache),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    assert "Pulled acme:common:fifo:1.0.0" in capsys.readouterr().out
    assert (out / "ip.toml").read_text(encoding="utf-8") == _MANIFEST


def test_yank_hides_version(tmp_path: Path) -> None:
    core = _core(tmp_path)
    registry_dir = tmp_path / "registry"
    assert cli.main(["publish", str(core / "ip.toml"), "--registry", str(registry_dir)]) == 0
    registry = LocalRegistry(registry_dir)
    ref = PackageRef.parse("acme:common:fifo")
    assert [str(v) for v in registry.versions(ref)] == ["acme:common:fifo:1.0.0"]
    assert cli.main(["yank", "acme:common:fifo:1.0.0", "--registry", str(registry_dir)]) == 0
    assert registry.versions(ref) == []


def test_yank_unpublished_version_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["yank", "acme:common:fifo:9.9.9", "--registry", str(tmp_path / "registry")])
    assert rc == 1
    assert "error:" in capsys.readouterr().err
