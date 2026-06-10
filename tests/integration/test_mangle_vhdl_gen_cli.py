"""Integration test: `hdlpkg gen` name-mangles coexisting VHDL packages (ghdl flow).

Mirrors the SystemVerilog coexistence test for VHDL: a shared `vbus` package at two
incompatible majors, with `vfifo` (^1) and `vlegacy` (^2) using it via
`use work.vbus.all`. Under `isolate_namespaces`, `gen` (ghdl toolflow) must rewrite
each package version to a unique name and route each consumer to its resolved version.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hdl_ip_packager import cli

pytestmark = pytest.mark.integration

_RTL = '\n[filesets.rtl]\nfiles = ["rtl/src.vhd"]\ntype = "vhdlSource"\n'


def _core(directory: Path, toml: str, vhd: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ip.toml").write_text(toml, encoding="utf-8")
    (directory / "rtl").mkdir(exist_ok=True)
    (directory / "rtl" / "src.vhd").write_text(vhd, encoding="utf-8")


def _scenario(root: Path) -> Path:
    for version, width in (("1.0.0", 8), ("1.1.0", 16), ("2.0.0", 32)):
        _core(
            root / f"vbus-{version}",
            f'[package]\nvendor="acme"\nlibrary="common"\nname="vbus"\nversion="{version}"\n'
            + _RTL,
            f"package vbus is\n  constant WIDTH : integer := {width};\nend package vbus;\n",
        )
    _core(
        root / "vfifo",
        '[package]\nvendor="acme"\nlibrary="ip"\nname="vfifo"\nversion="1.0.0"\ntop="vfifo"\n'
        '[dependencies]\n"acme:common:vbus" = "^1.0.0"\n' + _RTL,
        "use work.vbus.all;\nentity vfifo is end entity;\n",
    )
    _core(
        root / "vlegacy",
        '[package]\nvendor="acme"\nlibrary="ip"\nname="vlegacy"\nversion="1.0.0"\ntop="vlegacy"\n'
        '[dependencies]\n"acme:common:vbus" = "^2.0.0"\n' + _RTL,
        "use work.vbus.all;\nentity vlegacy is end entity;\n",
    )
    top = root / "top"
    _core(
        top,
        '[package]\nvendor="acme"\nlibrary="soc"\nname="vtop"\nversion="1.0.0"\ntop="vtop"\n'
        '[dependencies]\n"acme:ip:vfifo" = "^1.0.0"\n"acme:ip:vlegacy" = "^1.0.0"\n'
        '[resolution]\non-conflict = "isolate_namespaces"\n'
        '\n[filesets.rtl]\nfiles = ["rtl/src.vhd"]\ntype = "vhdlSource"\n'
        '[targets.sim]\ntoolflow = "ghdl"\nfilesets = ["rtl"]\ntop = "vtop"\n',
        "entity vtop is end entity;\n",
    )
    return top


def test_gen_mangles_coexisting_vhdl_packages(
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
    bus_v1 = (src / "acme_common_vbus_1.1.0" / "rtl" / "src.vhd").read_text()
    bus_v2 = (src / "acme_common_vbus_2.0.0" / "rtl" / "src.vhd").read_text()
    vfifo = (src / "acme_ip_vfifo_1.0.0" / "rtl" / "src.vhd").read_text()
    vlegacy = (src / "acme_ip_vlegacy_1.0.0" / "rtl" / "src.vhd").read_text()

    assert "package vbus__v1_1_0 is" in bus_v1
    assert "package vbus__v2_0_0 is" in bus_v2
    assert "use work.vbus__v1_1_0.all;" in vfifo  # vfifo (^1) -> 1.1.0
    assert "use work.vbus__v2_0_0.all;" in vlegacy  # vlegacy (^2) -> 2.0.0

    # The GHDL run script references the mangled copies under src/.
    script = (out / "run_ghdl.sh").read_text()
    assert src.as_posix() in script
