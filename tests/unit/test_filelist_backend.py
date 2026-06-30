"""Unit tests for FilelistBackend: ordered ``.f`` lists grouped by HDL type."""

from __future__ import annotations

import pytest

from hdlpkg.backends import EdaDesign, EdaFile, FilelistBackend

pytestmark = pytest.mark.unit


def _design(*files: tuple[str, str]) -> EdaDesign:
    return EdaDesign(
        name="top",
        toplevel="top",
        toolflow="questa",  # irrelevant: the filelist format never dispatches on toolflow
        files=tuple(EdaFile(path=p, file_type=ft, core="acme:lib:c:1.0.0") for p, ft in files),
    )


def test_groups_by_type_and_preserves_compile_order() -> None:
    design = _design(
        ("/cache/dep/pkg.vhd", "vhdl"),
        ("/cache/top/a.sv", "systemVerilog"),
        ("/cache/top/b.sv", "systemVerilog"),
    )
    out = FilelistBackend().generate(design)

    assert out["top.vhdl.f"] == "/cache/dep/pkg.vhd\n"
    # Order within a type is the design's order (dependencies first, root last).
    assert out["top.systemverilog.f"] == "/cache/top/a.sv\n/cache/top/b.sv\n"


def test_each_hdl_type_gets_its_own_filelist() -> None:
    out = FilelistBackend().generate(
        _design(("/c/a.v", "verilog"), ("/c/b.sv", "systemVerilog"), ("/c/c.vhd", "vhdl"))
    )
    assert set(out) == {"top.verilog.f", "top.systemverilog.f", "top.vhdl.f"}


def test_unknown_file_type_is_slugified_not_dropped() -> None:
    out = FilelistBackend().generate(_design(("/c/x.vhd", "vhdlSource-2008")))
    assert out == {"top.vhdlsource-2008.f": "/c/x.vhd\n"}


def test_empty_design_emits_no_filelists() -> None:
    assert FilelistBackend().generate(_design()) == {}
