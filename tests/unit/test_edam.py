"""Unit tests for the EDAM-like intermediate assembly (``build_eda_design``).

Pure, no filesystem: cores are built from inline manifests with fake roots, and we
assert the file ordering, fileset-selection, dedup, and metadata rules.
"""

from __future__ import annotations

import pytest

from hdl_ip_packager.backends import CoreSource, build_eda_design
from hdl_ip_packager.manifest import Manifest

pytestmark = pytest.mark.unit

FIFO = """\
[package]
vendor = "acme"
library = "common"
name = "fifo"
version = "1.0.0"

[filesets.rtl]
files = ["rtl/sync_fifo.sv"]
type = "systemVerilogSource"

[filesets.tb]
files = ["tb/sync_fifo_tb.sv"]
type = "systemVerilogSource"

[targets.sim]
toolflow = "verilator"
filesets = ["rtl", "tb"]
top = "sync_fifo_tb"
"""

UART = """\
[package]
vendor = "acme"
library = "comm"
name = "uart"
version = "1.2.0"
top = "uart_top"

[dependencies]
"acme:common:fifo" = "^1.0.0"

[filesets.rtl]
files = ["rtl/uart_top.sv", "rtl/uart_rx.sv"]
type = "systemVerilogSource"

[filesets.tb]
files = ["tb/uart_tb.sv"]
type = "systemVerilogSource"

[targets.sim]
toolflow = "verilator"
filesets = ["rtl", "tb"]
top = "uart_tb"

[targets.synth]
toolflow = "vivado"
filesets = ["rtl"]
"""


def _core(toml: str, root: str) -> CoreSource:
    return CoreSource(manifest=Manifest.from_str(toml), root=root)


def test_sim_target_includes_dep_rtl_then_root_filesets_in_order() -> None:
    design = build_eda_design(_core(UART, "u"), "sim", [_core(FIFO, "f")])
    assert [f.path for f in design.files] == [
        "f/rtl/sync_fifo.sv",  # dependency rtl first
        "u/rtl/uart_top.sv",
        "u/rtl/uart_rx.sv",
        "u/tb/uart_tb.sv",  # root testbench last
    ]
    assert design.name == "uart"
    assert design.toplevel == "uart_tb"  # the target's own top wins
    assert design.toolflow == "verilator"


def test_dependency_testbench_is_never_included() -> None:
    design = build_eda_design(_core(UART, "u"), "sim", [_core(FIFO, "f")])
    assert all("sync_fifo_tb" not in f.path for f in design.files)


def test_synth_target_excludes_testbench_and_falls_back_to_core_top() -> None:
    design = build_eda_design(_core(UART, "u"), "synth", [_core(FIFO, "f")])
    assert [f.path for f in design.files] == [
        "f/rtl/sync_fifo.sv",
        "u/rtl/uart_top.sv",
        "u/rtl/uart_rx.sv",
    ]
    assert design.toolflow == "vivado"
    assert design.toplevel == "uart_top"  # synth target has no top -> package top


def test_file_types_are_normalized() -> None:
    design = build_eda_design(_core(UART, "u"), "synth", [_core(FIFO, "f")])
    assert {f.file_type for f in design.files} == {"systemVerilog"}


def test_unknown_target_raises() -> None:
    with pytest.raises(ValueError, match="Unknown target 'nope'"):
        build_eda_design(_core(UART, "u"), "nope", [_core(FIFO, "f")])


def test_dependencies_are_topologically_ordered() -> None:
    # mid depends on leaf; provided in the "wrong" order, leaf must still come first.
    leaf = """\
[package]
vendor = "acme"
library = "x"
name = "leaf"
version = "1.0.0"
[filesets.rtl]
files = ["leaf.sv"]
type = "systemVerilogSource"
"""
    mid = """\
[package]
vendor = "acme"
library = "x"
name = "mid"
version = "1.0.0"
[dependencies]
"acme:x:leaf" = "^1.0.0"
[filesets.rtl]
files = ["mid.sv"]
type = "systemVerilogSource"
[targets.synth]
toolflow = "vivado"
filesets = ["rtl"]
"""
    top = """\
[package]
vendor = "acme"
library = "x"
name = "top"
version = "1.0.0"
top = "top"
[dependencies]
"acme:x:mid" = "^1.0.0"
[filesets.rtl]
files = ["top.sv"]
type = "systemVerilogSource"
[targets.synth]
toolflow = "vivado"
filesets = ["rtl"]
"""
    design = build_eda_design(_core(top, "t"), "synth", [_core(mid, "m"), _core(leaf, "l")])
    assert [f.path for f in design.files] == ["l/leaf.sv", "m/mid.sv", "t/top.sv"]


def test_duplicate_paths_are_deduplicated() -> None:
    # A dependency whose rtl file resolves to the same path as another's is kept once.
    a = """\
[package]
vendor = "acme"
library = "x"
name = "a"
version = "1.0.0"
[filesets.rtl]
files = ["shared.sv"]
type = "systemVerilogSource"
"""
    root = """\
[package]
vendor = "acme"
library = "x"
name = "root"
version = "1.0.0"
top = "root"
[filesets.rtl]
files = ["shared.sv"]
type = "systemVerilogSource"
[targets.synth]
toolflow = "vivado"
filesets = ["rtl"]
"""
    # Same root string for both so the joined paths collide.
    design = build_eda_design(_core(root, "same"), "synth", [_core(a, "same")])
    assert [f.path for f in design.files] == ["same/shared.sv"]
