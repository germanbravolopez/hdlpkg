"""Integration: `hdlpkg gen` name-mangles coexisting modules / interfaces / entities.

Companion to `test_mangle_gen_cli.py` (SV packages) and `test_mangle_vhdl_gen_cli.py`
(VHDL packages). Builds version-conflict scenarios for the *non-package* unit kinds and
checks that, under `isolate_namespaces`, `gen` rewrites each version's declaration to a
unique name and routes each consumer's instantiation/reference to the version it resolved
to, instead of refusing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hdlpkg import cli

pytestmark = pytest.mark.integration


def _core(directory: Path, toml: str, src_name: str, src: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ip.toml").write_text(toml, encoding="utf-8")
    (directory / "rtl").mkdir(exist_ok=True)
    (directory / "rtl" / src_name).write_text(src, encoding="utf-8")


def _gen(tmp_path: Path, top: Path, target: str) -> Path:
    out = tmp_path / "gen"
    rc = cli.main(
        ["gen", target, str(top / "ip.toml"), "--search", str(tmp_path), "--output", str(out)]
    )
    assert rc == 0
    return out / "src"


def test_gen_mangles_coexisting_sv_interfaces(tmp_path: Path) -> None:
    rtl = '\n[filesets.rtl]\nfiles = ["rtl/src.sv"]\ntype = "systemVerilogSource"\n'
    for version in ("1.0.0", "2.0.0"):
        _core(
            tmp_path / f"ifc-{version}",
            f'[package]\nvendor="acme"\nlibrary="common"\nname="bus_if"\nversion="{version}"\n'
            + rtl,
            "src.sv",
            "interface bus_if; endinterface\n",
        )
    for name, constraint in (("fifo", "^1.0.0"), ("legacy", "^2.0.0")):
        _core(
            tmp_path / name,
            f'[package]\nvendor="acme"\nlibrary="ip"\nname="{name}"\nversion="1.0.0"\n'
            f'[dependencies]\n"acme:common:bus_if" = "{constraint}"\n' + rtl,
            "src.sv",
            f"module {name} (bus_if b); bus_if u_if (); endmodule\n",
        )
    top = tmp_path / "top"
    _core(
        top,
        '[package]\nvendor="acme"\nlibrary="soc"\nname="top"\nversion="1.0.0"\ntop="soc_top"\n'
        '[dependencies]\n"acme:ip:fifo" = "^1.0.0"\n"acme:ip:legacy" = "^1.0.0"\n'
        '[resolution]\non-conflict = "isolate_namespaces"\n'
        + rtl
        + '[targets.sim]\ntoolflow = "verilator"\nfilesets = ["rtl"]\ntop = "soc_top"\n',
        "src.sv",
        "module soc_top; fifo u_f (); legacy u_l (); endmodule\n",
    )

    src = _gen(tmp_path, top, "sim")

    def rd(core: str) -> str:
        return (src / core / "rtl" / "src.sv").read_text(encoding="utf-8")

    assert "interface bus_if_v1_0_0;" in rd("acme_common_bus_if_1.0.0")
    assert "interface bus_if_v2_0_0;" in rd("acme_common_bus_if_2.0.0")
    # each consumer routed to the version it resolved to
    assert "module fifo (bus_if_v1_0_0 b); bus_if_v1_0_0 u_if ();" in rd("acme_ip_fifo_1.0.0")
    assert "module legacy (bus_if_v2_0_0 b); bus_if_v2_0_0 u_if ();" in rd("acme_ip_legacy_1.0.0")


def test_gen_mangles_coexisting_vhdl_entities(tmp_path: Path) -> None:
    rtl = '\n[filesets.rtl]\nfiles = ["rtl/src.vhd"]\ntype = "vhdlSource"\n'
    entity = "entity vbus is end entity vbus;\narchitecture rtl of vbus is begin end rtl;\n"
    for version in ("1.0.0", "2.0.0"):
        _core(
            tmp_path / f"vbus-{version}",
            f'[package]\nvendor="acme"\nlibrary="common"\nname="vbus"\nversion="{version}"\n' + rtl,
            "src.vhd",
            entity,
        )
    for name, constraint in (("vfifo", "^1.0.0"), ("vlegacy", "^2.0.0")):
        _core(
            tmp_path / name,
            f'[package]\nvendor="acme"\nlibrary="ip"\nname="{name}"\nversion="1.0.0"\n'
            f'[dependencies]\n"acme:common:vbus" = "{constraint}"\n' + rtl,
            "src.vhd",
            f"entity {name} is end entity {name};\n"
            f"architecture rtl of {name} is begin\n  u : entity work.vbus;\nend rtl;\n",
        )
    top = tmp_path / "top"
    _core(
        top,
        '[package]\nvendor="acme"\nlibrary="soc"\nname="vtop"\nversion="1.0.0"\ntop="vtop"\n'
        '[dependencies]\n"acme:ip:vfifo" = "^1.0.0"\n"acme:ip:vlegacy" = "^1.0.0"\n'
        '[resolution]\non-conflict = "isolate_namespaces"\n'
        + rtl
        + '[targets.sim]\ntoolflow = "ghdl"\nfilesets = ["rtl"]\ntop = "vtop"\n',
        "src.vhd",
        "entity vtop is end entity vtop;\n"
        "architecture rtl of vtop is begin\n  uf : entity work.vfifo;\n"
        "  ul : entity work.vlegacy;\nend rtl;\n",
    )

    src = _gen(tmp_path, top, "sim")

    def rd(core: str) -> str:
        return (src / core / "rtl" / "src.vhd").read_text(encoding="utf-8")

    assert "entity vbus_v1_0_0 is" in rd("acme_common_vbus_1.0.0")
    assert "entity vbus_v2_0_0 is" in rd("acme_common_vbus_2.0.0")
    assert "entity work.vbus_v1_0_0;" in rd("acme_ip_vfifo_1.0.0")  # vfifo (^1) -> 1.0.0
    assert "entity work.vbus_v2_0_0;" in rd("acme_ip_vlegacy_1.0.0")  # vlegacy (^2) -> 2.0.0
