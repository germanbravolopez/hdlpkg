"""Unit tests for the tool-flow backends (Verilator, Vivado) and the registry."""

from __future__ import annotations

import pytest

from hdl_ip_packager.backends import (
    EdaDesign,
    EdaFile,
    get_backend,
    supported_toolflows,
)
from hdl_ip_packager.backends.verilator import VerilatorBackend
from hdl_ip_packager.backends.vivado import VivadoBackend
from hdl_ip_packager.exceptions import BackendError

pytestmark = pytest.mark.unit


def _design(files: tuple[EdaFile, ...], toolflow: str, top: str | None = "top") -> EdaDesign:
    return EdaDesign(name="dut", toplevel=top, toolflow=toolflow, files=files)


SV = EdaFile(path="a/top.sv", file_type="systemVerilog", core="acme:x:dut:1.0.0")
V = EdaFile(path="a/legacy.v", file_type="verilog", core="acme:x:dut:1.0.0")
VHDL = EdaFile(path="a/old.vhd", file_type="vhdl", core="acme:x:dut:1.0.0")


# ------------------------------------------------------------------- Verilator
def test_verilator_emits_vc_with_top_and_files() -> None:
    out = VerilatorBackend().generate(_design((SV, V), "verilator"))
    assert set(out) == {"dut.vc"}
    body = out["dut.vc"]
    assert "--top-module top" in body
    assert "a/top.sv" in body
    assert "a/legacy.v" in body


def test_verilator_rejects_vhdl() -> None:
    with pytest.raises(BackendError, match="vhdl"):
        VerilatorBackend().generate(_design((SV, VHDL), "verilator"))


def test_verilator_requires_a_top() -> None:
    with pytest.raises(BackendError, match="top module"):
        VerilatorBackend().generate(_design((SV,), "verilator", top=None))


# ---------------------------------------------------------------------- Vivado
def test_vivado_emits_tcl_with_read_commands_and_top() -> None:
    out = VivadoBackend().generate(_design((SV, V, VHDL), "vivado"))
    assert set(out) == {"dut.tcl"}
    body = out["dut.tcl"]
    assert 'read_verilog -sv "a/top.sv"' in body
    assert 'read_verilog "a/legacy.v"' in body
    assert 'read_vhdl "a/old.vhd"' in body
    assert "set_property top top [current_fileset]" in body
    assert "update_compile_order" in body


def test_vivado_without_top_omits_set_property() -> None:
    body = VivadoBackend().generate(_design((SV,), "vivado", top=None))["dut.tcl"]
    assert "set_property top" not in body


def test_vivado_rejects_unknown_file_type() -> None:
    weird = EdaFile(path="a/x.c", file_type="cSource", core="acme:x:dut:1.0.0")
    with pytest.raises(BackendError, match="cSource"):
        VivadoBackend().generate(_design((weird,), "vivado"))


# -------------------------------------------------------------------- registry
def test_get_backend_returns_the_right_backend() -> None:
    assert isinstance(get_backend("verilator"), VerilatorBackend)
    assert isinstance(get_backend("vivado"), VivadoBackend)


def test_get_backend_unknown_raises() -> None:
    with pytest.raises(BackendError, match="No backend for tool flow 'icarus'"):
        get_backend("icarus")


def test_supported_toolflows_lists_both() -> None:
    assert supported_toolflows() == ["verilator", "vivado"]
