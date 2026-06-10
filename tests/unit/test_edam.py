"""Unit tests for the EDAM-like intermediate assembly (``build_eda_design``).

Pure, no filesystem: cores are built from inline manifests with fake roots, and we
assert the file ordering, fileset-selection, dedup, and metadata rules.
"""

from __future__ import annotations

import pytest

from hdl_ip_packager.backends import CoreSource, build_eda_design
from hdl_ip_packager.exceptions import BackendError
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


def test_fileset_depend_is_pulled_in_before_the_fileset() -> None:
    # rtl declares depend = ["pkg"]; selecting rtl must emit pkg first.
    toml = """\
[package]
vendor = "acme"
library = "x"
name = "withpkg"
version = "1.0.0"
top = "core"
[filesets.pkg]
files = ["pkg.sv"]
type = "systemVerilogSource"
[filesets.rtl]
files = ["core.sv"]
type = "systemVerilogSource"
depend = ["pkg"]
[targets.synth]
toolflow = "vivado"
filesets = ["rtl"]
"""
    design = build_eda_design(_core(toml, "w"), "synth", [])
    assert [f.path for f in design.files] == ["w/pkg.sv", "w/core.sv"]


def test_dependency_export_honors_fileset_depend() -> None:
    # A dependency's rtl depends on a pkg fileset; the export must include pkg too.
    dep = """\
[package]
vendor = "acme"
library = "x"
name = "lib"
version = "1.0.0"
[filesets.pkg]
files = ["lib_pkg.sv"]
type = "systemVerilogSource"
[filesets.rtl]
files = ["lib.sv"]
type = "systemVerilogSource"
depend = ["pkg"]
"""
    root = """\
[package]
vendor = "acme"
library = "x"
name = "app"
version = "1.0.0"
top = "app"
[dependencies]
"acme:x:lib" = "^1.0.0"
[filesets.rtl]
files = ["app.sv"]
type = "systemVerilogSource"
[targets.synth]
toolflow = "vivado"
filesets = ["rtl"]
"""
    design = build_eda_design(_core(root, "a"), "synth", [_core(dep, "l")])
    assert [f.path for f in design.files] == ["l/lib_pkg.sv", "l/lib.sv", "a/app.sv"]


def test_fileset_depend_cycle_is_safe() -> None:
    # Mutually-dependent filesets must not loop; both still appear once.
    toml = """\
[package]
vendor = "acme"
library = "x"
name = "cyc"
version = "1.0.0"
top = "a"
[filesets.a]
files = ["a.sv"]
type = "systemVerilogSource"
depend = ["b"]
[filesets.b]
files = ["b.sv"]
type = "systemVerilogSource"
depend = ["a"]
[targets.synth]
toolflow = "vivado"
filesets = ["a"]
"""
    paths = [f.path for f in build_eda_design(_core(toml, "c"), "synth", []).files]
    assert sorted(paths) == ["c/a.sv", "c/b.sv"]
    assert len(paths) == 2  # no duplication despite the cycle


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


def test_two_versions_of_one_package_are_refused() -> None:
    # gen cannot host two versions of one package (no name-mangling) -> refuse.
    bus1 = """\
[package]
vendor = "acme"
library = "common"
name = "bus"
version = "1.0.0"
[filesets.rtl]
files = ["bus.sv"]
type = "systemVerilogSource"
"""
    bus2 = bus1.replace('version = "1.0.0"', 'version = "2.0.0"')
    root = """\
[package]
vendor = "acme"
library = "x"
name = "root"
version = "1.0.0"
top = "root"
[filesets.rtl]
files = ["root.sv"]
type = "systemVerilogSource"
[targets.synth]
toolflow = "vivado"
filesets = ["rtl"]
"""
    with pytest.raises(BackendError, match="two versions of acme:common:bus"):
        build_eda_design(_core(root, "r"), "synth", [_core(bus1, "b1"), _core(bus2, "b2")])
