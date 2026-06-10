"""Integration test: `hdlpkg gen` name-mangles coexisting SystemVerilog packages.

Builds a package-conflict scenario in a temp tree -- a shared `bus_pkg` at two
incompatible majors, with `fifo` (^1) and `legacy` (^2) importing it -- and checks
that, under `isolate_namespaces`, `gen` rewrites each package version to a unique
name and routes each consumer to the version it resolved to, instead of refusing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hdl_ip_packager import cli

pytestmark = pytest.mark.integration


def _core(directory: Path, toml: str, sv: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ip.toml").write_text(toml, encoding="utf-8")
    (directory / "rtl").mkdir(exist_ok=True)
    (directory / "rtl" / "src.sv").write_text(sv, encoding="utf-8")


_RTL = '\n[filesets.rtl]\nfiles = ["rtl/src.sv"]\ntype = "systemVerilogSource"\n'


def _scenario(root: Path) -> Path:
    for version in ("1.0.0", "1.1.0", "2.0.0"):
        _core(
            root / f"bus-{version}",
            f'[package]\nvendor="acme"\nlibrary="common"\nname="bus_pkg"\nversion="{version}"\n'
            + _RTL,
            f"package bus_pkg;\n  localparam int V = {version[0]};\nendpackage\n",
        )
    _core(
        root / "fifo",
        '[package]\nvendor="acme"\nlibrary="ip"\nname="fifo"\nversion="1.0.0"\ntop="fifo"\n'
        '[dependencies]\n"acme:common:bus_pkg" = "^1.0.0"\n' + _RTL,
        "module fifo; import bus_pkg::*; endmodule\n",
    )
    _core(
        root / "legacy",
        '[package]\nvendor="acme"\nlibrary="ip"\nname="legacy"\nversion="1.0.0"\ntop="legacy"\n'
        '[dependencies]\n"acme:common:bus_pkg" = "^2.0.0"\n' + _RTL,
        "module legacy; import bus_pkg::*; endmodule\n",
    )
    top = root / "top"
    _core(
        top,
        '[package]\nvendor="acme"\nlibrary="soc"\nname="top"\nversion="1.0.0"\ntop="soc_top"\n'
        '[dependencies]\n"acme:ip:fifo" = "^1.0.0"\n"acme:ip:legacy" = "^1.0.0"\n'
        '[resolution]\non-conflict = "isolate_namespaces"\n'
        '\n[filesets.rtl]\nfiles = ["rtl/src.sv"]\ntype = "systemVerilogSource"\n'
        '[targets.sim]\ntoolflow = "verilator"\nfilesets = ["rtl"]\ntop = "soc_top"\n',
        "module soc_top; fifo u_f(); legacy u_l(); endmodule\n",
    )
    return top


def test_gen_mangles_coexisting_packages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    top = _scenario(tmp_path)
    out = tmp_path / "gen"
    rc = cli.main(
        ["gen", "sim", str(top / "ip.toml"), "--search", str(tmp_path), "--output", str(out)]
    )
    assert rc == 0
    assert "name-mangled" in capsys.readouterr().err

    src = out / "src"
    bus_v1 = (src / "acme_common_bus_pkg_1.1.0" / "rtl" / "src.sv").read_text()
    bus_v2 = (src / "acme_common_bus_pkg_2.0.0" / "rtl" / "src.sv").read_text()
    fifo = (src / "acme_ip_fifo_1.0.0" / "rtl" / "src.sv").read_text()
    legacy = (src / "acme_ip_legacy_1.0.0" / "rtl" / "src.sv").read_text()

    assert "package bus_pkg__v1_1_0;" in bus_v1
    assert "package bus_pkg__v2_0_0;" in bus_v2
    assert "import bus_pkg__v1_1_0::*;" in fifo  # fifo (^1) -> 1.1.0
    assert "import bus_pkg__v2_0_0::*;" in legacy  # legacy (^2) -> 2.0.0

    # The generated .vc references the mangled copies under src/, and the original
    # source on disk is left untouched.
    vc = (out / "top.vc").read_text()
    assert src.as_posix() in vc
    original = (tmp_path / "bus-1.1.0" / "rtl" / "src.sv").read_text()
    assert original == "package bus_pkg;\n  localparam int V = 1;\nendpackage\n"
