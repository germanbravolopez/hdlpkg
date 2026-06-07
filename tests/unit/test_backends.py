"""Unit tests for the tool-flow backends (Verilator, Vivado) and the registry."""

from __future__ import annotations

import pytest

from hdl_ip_packager.backends import (
    EdaDesign,
    EdaFile,
    get_backend,
    supported_toolflows,
)
from hdl_ip_packager.backends.ghdl import GhdlBackend
from hdl_ip_packager.backends.icarus import IcarusBackend
from hdl_ip_packager.backends.verilator import VerilatorBackend
from hdl_ip_packager.backends.vivado import VivadoBackend
from hdl_ip_packager.backends.yosys import YosysBackend
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
    with pytest.raises(BackendError, match="needs a top"):
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


# --------------------------------------------------------------------- Icarus
def test_icarus_emits_command_file_and_run_script() -> None:
    out = IcarusBackend().generate(_design((SV, V), "icarus"))
    assert set(out) == {"dut.cmd", "run_iverilog.sh"}
    assert out["dut.cmd"] == "a/top.sv\na/legacy.v\n"
    assert "-s top" in out["run_iverilog.sh"]
    assert "vvp dut.vvp" in out["run_iverilog.sh"]


def test_icarus_rejects_vhdl() -> None:
    with pytest.raises(BackendError, match="vhdl"):
        IcarusBackend().generate(_design((SV, VHDL), "icarus"))


# ----------------------------------------------------------------------- GHDL
def test_ghdl_emits_analyze_elaborate_run() -> None:
    body = GhdlBackend().generate(_design((VHDL,), "ghdl"))["run_ghdl.sh"]
    assert 'ghdl -a --std=08 "a/old.vhd"' in body
    assert "ghdl -e --std=08 top" in body
    assert "ghdl -r --std=08 top" in body


def test_ghdl_rejects_non_vhdl() -> None:
    with pytest.raises(BackendError, match="cannot handle"):
        GhdlBackend().generate(_design((SV,), "ghdl"))


# ---------------------------------------------------------------------- Yosys
def test_yosys_emits_synth_script() -> None:
    body = YosysBackend().generate(_design((SV, V), "yosys"))["dut.ys"]
    assert 'read_verilog -sv "a/top.sv"' in body
    assert 'read_verilog "a/legacy.v"' in body
    assert "synth -top top" in body


def test_yosys_rejects_vhdl() -> None:
    with pytest.raises(BackendError, match="vhdl"):
        YosysBackend().generate(_design((VHDL,), "yosys"))


# ---------------------------------------------------- shared guards (hardening)
def test_backends_reject_an_unsafe_top_name() -> None:
    # A top with a space/metacharacter must not be interpolated into a script.
    with pytest.raises(BackendError, match="unsafe top"):
        VerilatorBackend().generate(_design((SV,), "verilator", top="foo bar"))
    with pytest.raises(BackendError, match="unsafe top"):
        IcarusBackend().generate(_design((SV,), "icarus", top="rm -rf /"))
    with pytest.raises(BackendError, match="unsafe top"):
        YosysBackend().generate(_design((SV,), "yosys", top="a;b"))


def test_vivado_rejects_an_unsafe_top_when_present() -> None:
    with pytest.raises(BackendError, match="unsafe top"):
        VivadoBackend().generate(_design((SV,), "vivado", top="bad name"))


# -------------------------------------------------------------------- registry
def test_get_backend_returns_the_right_backend() -> None:
    assert isinstance(get_backend("verilator"), VerilatorBackend)
    assert isinstance(get_backend("vivado"), VivadoBackend)
    assert isinstance(get_backend("icarus"), IcarusBackend)
    assert isinstance(get_backend("ghdl"), GhdlBackend)
    assert isinstance(get_backend("yosys"), YosysBackend)


def test_get_backend_unknown_raises() -> None:
    with pytest.raises(BackendError, match="No backend for tool flow 'modelsim'"):
        get_backend("modelsim")


def test_supported_toolflows_lists_all() -> None:
    assert supported_toolflows() == ["ghdl", "icarus", "verilator", "vivado", "yosys"]
