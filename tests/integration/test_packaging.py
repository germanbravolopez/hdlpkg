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

from hdlpkg.exceptions import PackagingError
from hdlpkg.lockfile import sha256_digest
from hdlpkg.manifest import Manifest
from hdlpkg.packaging import (
    artifact_filename,
    expand_fileset_files,
    extract_ipkg,
    manifest_from_ipkg,
    pack_core,
)
from hdlpkg.vlnv import Vlnv

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


def test_expand_glob_matches_files_recursively_and_sorted(tmp_path: Path) -> None:
    (tmp_path / "rtl" / "sub").mkdir(parents=True)
    (tmp_path / "rtl" / "b.vhd").write_text("b", encoding="utf-8")
    (tmp_path / "rtl" / "a.vhd").write_text("a", encoding="utf-8")
    (tmp_path / "rtl" / "sub" / "c.vhd").write_text("c", encoding="utf-8")
    (tmp_path / "rtl" / "notes.txt").write_text("skip", encoding="utf-8")
    files = expand_fileset_files(tmp_path, "vhdl", ["rtl/**/*.vhd"])
    assert files == ["rtl/a.vhd", "rtl/b.vhd", "rtl/sub/c.vhd"]  # sorted, .txt excluded


def test_expand_directory_includes_every_file(tmp_path: Path) -> None:
    (tmp_path / "ip" / "sub").mkdir(parents=True)
    (tmp_path / "ip" / "x.xml").write_text("x", encoding="utf-8")
    (tmp_path / "ip" / "sub" / "y.xml").write_text("y", encoding="utf-8")
    assert expand_fileset_files(tmp_path, "ipxact", ["ip"]) == ["ip/sub/y.xml", "ip/x.xml"]


def test_expand_literal_is_preserved_and_deduplicated(tmp_path: Path) -> None:
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "top.sv").write_text("t", encoding="utf-8")
    # A literal path is kept verbatim (a missing one still surfaces later, on read);
    # a literal repeated by a glob is de-duplicated, author order preserved.
    files = expand_fileset_files(tmp_path, "rtl", ["rtl/top.sv", "rtl/*.sv"])
    assert files == ["rtl/top.sv"]


def test_expand_empty_glob_raises(tmp_path: Path) -> None:
    with pytest.raises(PackagingError, match="matched no files"):
        expand_fileset_files(tmp_path, "rtl", ["rtl/**/*.sv"])


def test_expand_rejects_escaping_pattern(tmp_path: Path) -> None:
    with pytest.raises(PackagingError, match="escapes the core directory"):
        expand_fileset_files(tmp_path, "rtl", ["../*.sv"])


def test_pack_expands_glob_and_directory_filesets(tmp_path: Path) -> None:
    manifest_text = (
        '[package]\nvendor="acme"\nlibrary="common"\nname="gen"\nversion="1.0.0"\n'
        '[filesets.vhdl]\nfiles = ["rtl/**/*.vhd"]\ntype = "vhdlSource"\n'
        '[filesets.ipxact]\nfiles = ["ip"]\ntype = "user"\n'
    )
    (tmp_path / "rtl" / "sub").mkdir(parents=True)
    (tmp_path / "ip").mkdir()
    (tmp_path / "ip.toml").write_text(manifest_text, encoding="utf-8")
    (tmp_path / "rtl" / "a.vhd").write_text("a", encoding="utf-8")
    (tmp_path / "rtl" / "sub" / "b.vhd").write_text("b", encoding="utf-8")
    (tmp_path / "rtl" / "skip.txt").write_text("skip", encoding="utf-8")
    (tmp_path / "ip" / "scaler.xml").write_text("<c/>", encoding="utf-8")
    data = pack_core(Manifest.from_str(manifest_text), tmp_path)
    dest = extract_ipkg(data, tmp_path / "out")
    packed = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert packed == ["ip.toml", "ip/scaler.xml", "rtl/a.vhd", "rtl/sub/b.vhd"]


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
