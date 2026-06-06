"""Integration test: ``hdlpkg gen`` over the bundled examples, end to end.

Resolves the UART example's FIFO dependency, assembles the design, renders the
tool inputs, and writes them out -- exercising resolve -> assemble -> backend ->
write. Marked ``integration`` (filesystem + multi-module).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hdl_ip_packager import cli

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
UART_MANIFEST = EXAMPLES / "uart" / "ip.toml"


def test_gen_verilator_sim_target(tmp_path: Path, capsys) -> None:
    rc = cli.main(
        ["gen", "sim", str(UART_MANIFEST), "--search", str(EXAMPLES), "--output", str(tmp_path)]
    )
    assert rc == 0
    vc = (tmp_path / "uart.vc").read_text(encoding="utf-8")
    assert "--top-module uart_tb" in vc
    assert "sync_fifo.sv" in vc  # the FIFO dependency's rtl
    assert "uart_top.sv" in vc
    assert "uart_tb.sv" in vc  # the root testbench (sim target)
    assert "sync_fifo_tb.sv" not in vc  # but never the dependency's testbench
    assert "uart.vc" in capsys.readouterr().out


def test_gen_vivado_synth_target(tmp_path: Path) -> None:
    rc = cli.main(
        ["gen", "synth", str(UART_MANIFEST), "--search", str(EXAMPLES), "--output", str(tmp_path)]
    )
    assert rc == 0
    tcl = (tmp_path / "uart.tcl").read_text(encoding="utf-8")
    assert "read_verilog -sv" in tcl
    assert "sync_fifo.sv" in tcl
    assert "set_property top uart_top" in tcl
    assert "uart_tb.sv" not in tcl  # synth target excludes the testbench


def test_gen_unknown_target_fails(tmp_path: Path, capsys) -> None:
    rc = cli.main(
        ["gen", "nope", str(UART_MANIFEST), "--search", str(EXAMPLES), "--output", str(tmp_path)]
    )
    assert rc == 1
    assert "Unknown target" in capsys.readouterr().err
