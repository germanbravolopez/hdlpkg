"""Tests for the .ipkg packaging layer.

Packing reads a core directory and unpacking writes one, so these are integration
tests. They cover determinism (byte-identical output), the pack/extract round-trip,
reading the manifest back out, and the failure modes (missing fileset file, unsafe
archive paths).
"""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

import pytest

from hdl_ip_packager.exceptions import PackagingError
from hdl_ip_packager.lockfile import sha256_digest
from hdl_ip_packager.manifest import Manifest
from hdl_ip_packager.packaging import (
    artifact_filename,
    extract_ipkg,
    manifest_from_ipkg,
    pack_core,
)
from hdl_ip_packager.vlnv import Vlnv

pytestmark = pytest.mark.integration

_MANIFEST = (
    "[package]\n"
    'vendor = "acme"\n'
    'library = "common"\n'
    'name = "fifo"\n'
    'version = "1.0.0"\n'
    "[filesets.rtl]\n"
    'files = ["rtl/fifo.sv"]\n'
)


def _make_core(root: Path) -> Manifest:
    (root / "rtl").mkdir(parents=True)
    (root / "ip.toml").write_text(_MANIFEST, encoding="utf-8")
    (root / "rtl" / "fifo.sv").write_text("module fifo; endmodule\n", encoding="utf-8")
    return Manifest.from_str(_MANIFEST)


def test_artifact_filename() -> None:
    assert artifact_filename(Vlnv.parse("acme:common:fifo:1.0.0")) == "acme-common-fifo-1.0.0.ipkg"


def test_pack_is_deterministic(tmp_path: Path) -> None:
    manifest = _make_core(tmp_path)
    first = pack_core(manifest, tmp_path)
    second = pack_core(manifest, tmp_path)
    assert first == second
    assert sha256_digest(first).startswith("sha256:")


def test_pack_extract_round_trip(tmp_path: Path) -> None:
    manifest = _make_core(tmp_path / "core")
    data = pack_core(manifest, tmp_path / "core")
    dest = extract_ipkg(data, tmp_path / "out")
    assert (dest / "ip.toml").read_text(encoding="utf-8") == _MANIFEST
    assert (dest / "rtl" / "fifo.sv").read_text(encoding="utf-8") == "module fifo; endmodule\n"


def test_manifest_from_ipkg(tmp_path: Path) -> None:
    manifest = _make_core(tmp_path)
    assert manifest_from_ipkg(pack_core(manifest, tmp_path)).vlnv == manifest.vlnv


def test_pack_missing_fileset_file_raises(tmp_path: Path) -> None:
    (tmp_path / "ip.toml").write_text(_MANIFEST, encoding="utf-8")  # rtl/fifo.sv absent
    manifest = Manifest.from_str(_MANIFEST)
    with pytest.raises(PackagingError, match="missing file"):
        pack_core(manifest, tmp_path)


def test_pack_rejects_fileset_path_escaping_core(tmp_path: Path) -> None:
    escaping = (
        '[package]\nvendor="a"\nlibrary="b"\nname="c"\nversion="1.0.0"\n'
        '[filesets.rtl]\nfiles = ["../outside.sv"]\n'
    )
    (tmp_path / "ip.toml").write_text(escaping, encoding="utf-8")
    with pytest.raises(PackagingError, match="escapes the core directory"):
        pack_core(Manifest.from_str(escaping), tmp_path)


def test_extract_rejects_path_traversal(tmp_path: Path) -> None:
    # Craft a malicious archive whose member escapes the destination.
    raw = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        info = tarfile.TarInfo("../evil.txt")
        payload = b"pwned"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(PackagingError, match="unsafe path"):
        extract_ipkg(raw.getvalue(), tmp_path / "out")


def test_extract_rejects_non_ipkg_bytes(tmp_path: Path) -> None:
    with pytest.raises(PackagingError, match="Not a valid"):
        extract_ipkg(b"not an archive", tmp_path / "out")
