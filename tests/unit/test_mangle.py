"""Unit tests for the SystemVerilog package mangler (pure, no I/O).

Covers the comment/string-aware rewriter (only unambiguous package positions are
touched), the declaration scanners, and the multi-version planner (rename maps,
per-consumer resolution, and the refusals for module collisions / VHDL).
"""

from __future__ import annotations

import pytest

from hdl_ip_packager.exceptions import BackendError
from hdl_ip_packager.mangle import (
    GenCore,
    GenSourceFile,
    declared_modules,
    declared_packages,
    declared_vhdl_entities,
    declared_vhdl_packages,
    mangled_name,
    plan_package_mangling,
    rewrite_sv_packages,
    rewrite_vhdl_packages,
)
from hdl_ip_packager.manifest import Manifest
from hdl_ip_packager.version import Version

pytestmark = pytest.mark.unit


class TestScanners:
    def test_declared_packages(self) -> None:
        src = "// package not_this\npackage bus_pkg;\nendpackage : bus_pkg\n"
        assert declared_packages(src) == ("bus_pkg",)

    def test_declared_modules_and_interfaces(self) -> None:
        src = "module top; endmodule\ninterface bus_if; endinterface\n"
        assert set(declared_modules(src)) == {"top", "bus_if"}

    def test_mangled_name_is_sv_safe(self) -> None:
        assert mangled_name("bus_pkg", Version.parse("1.1.0")) == "bus_pkg__v1_1_0"
        assert mangled_name("p", Version.parse("2.0.0-rc.1")) == "p__v2_0_0_rc_1"


_RENAMES = {"bus_pkg": "bus_pkg__v1"}


class TestRewrite:
    def test_rewrites_declaration_and_end_label(self) -> None:
        out = rewrite_sv_packages("package bus_pkg;\nendpackage : bus_pkg\n", _RENAMES)
        assert "package bus_pkg__v1;" in out
        assert "endpackage : bus_pkg__v1" in out

    def test_rewrites_import_and_scoped_reference(self) -> None:
        assert rewrite_sv_packages("import bus_pkg::*;", _RENAMES) == "import bus_pkg__v1::*;"
        assert rewrite_sv_packages("x=bus_pkg::W;", _RENAMES) == "x=bus_pkg__v1::W;"

    def test_leaves_comments_and_strings_untouched(self) -> None:
        src = '// use bus_pkg here\n/* bus_pkg */\nstring s = "bus_pkg::x";\n'
        assert rewrite_sv_packages(src, _RENAMES) == src

    def test_leaves_a_coincidental_signal_name_untouched(self) -> None:
        src = "logic bus_pkg;\nassign bus_pkg = 1;\n"
        assert rewrite_sv_packages(src, _RENAMES) == src

    def test_no_renames_is_identity(self) -> None:
        src = "package bus_pkg;\nendpackage\n"
        assert rewrite_sv_packages(src, {}) == src


class TestVhdl:
    def test_declared_packages_are_lowercased_and_deduped(self) -> None:
        src = "package Bus_Pkg is\nend package Bus_Pkg;\npackage body bus_pkg is\nend;\n"
        assert declared_vhdl_packages(src) == ("bus_pkg",)

    def test_declared_entities_ignore_instantiations(self) -> None:
        src = "entity radio is end; L: entity work.radio port map();\n"
        assert declared_vhdl_entities(src) == ("radio",)

    def test_rewrites_declaration_body_and_end_labels(self) -> None:
        src = "package bus is\nend package bus;\npackage body bus is\nend package body bus;\n"
        out = rewrite_vhdl_packages(src, {"bus": "bus__v1"})
        assert "package bus__v1 is" in out
        assert "end package bus__v1;" in out
        assert "package body bus__v1 is" in out
        assert "end package body bus__v1;" in out

    def test_rewrites_use_reference_case_insensitively(self) -> None:
        out = rewrite_vhdl_packages("use WORK.BUS.all;", {"bus": "bus__v1"})
        assert out == "use WORK.bus__v1.all;"

    def test_leaves_comments_and_coincidental_signal_untouched(self) -> None:
        src = "-- use work.bus.all\nsignal bus : integer;\n"
        assert rewrite_vhdl_packages(src, {"bus": "bus__v1"}) == src

    def test_leaves_a_named_library_reference_untouched(self) -> None:
        # Only `work.<pkg>` is rewritten (everything is analyzed into `work`); a named
        # library reference is left alone (a documented limitation).
        src = "use other_lib.bus.all;\n"
        assert rewrite_vhdl_packages(src, {"bus": "bus__v1"}) == src


def _core(toml: str, files: dict[str, str], language: str = "systemverilog") -> GenCore:
    manifest = Manifest.from_str(toml)
    gen_files = tuple(
        GenSourceFile(key=(str(manifest.vlnv), rel), text=text, language=language)
        for rel, text in files.items()
    )
    return GenCore(manifest=manifest, files=gen_files)


_BUS = '[package]\nvendor="acme"\nlibrary="common"\nname="bus"\nversion="{v}"\n'
_CONSUMER = (
    '[package]\nvendor="acme"\nlibrary="ip"\nname="{n}"\nversion="1.0.0"\n'
    '[dependencies]\n"acme:common:bus" = "{c}"\n'
)


class TestPlanner:
    def _scenario(self) -> list[GenCore]:
        return [
            _core(_BUS.format(v="1.1.0"), {"bus.sv": "package bus;\nendpackage\n"}),
            _core(_BUS.format(v="2.0.0"), {"bus.sv": "package bus;\nendpackage\n"}),
            _core(
                _CONSUMER.format(n="fifo", c="^1.0.0"),
                {"fifo.sv": "module fifo; import bus::*; endmodule\n"},
            ),
            _core(
                _CONSUMER.format(n="legacy", c="^2.0.0"),
                {"legacy.sv": "module legacy; import bus::*; endmodule\n"},
            ),
        ]

    def test_mangles_each_version_and_routes_consumers(self) -> None:
        plan = plan_package_mangling(self._scenario())
        assert plan.renamed == {"bus": ("bus__v1_1_0", "bus__v2_0_0")}
        # each package version keeps its own mangled name
        assert "package bus__v1_1_0;" in plan.rewritten[("acme:common:bus:1.1.0", "bus.sv")]
        assert "package bus__v2_0_0;" in plan.rewritten[("acme:common:bus:2.0.0", "bus.sv")]
        # each consumer is routed to the version it resolved to
        assert "import bus__v1_1_0::*;" in plan.rewritten[("acme:ip:fifo:1.0.0", "fifo.sv")]
        assert "import bus__v2_0_0::*;" in plan.rewritten[("acme:ip:legacy:1.0.0", "legacy.sv")]

    def test_single_version_design_is_untouched(self) -> None:
        cores = [
            _core(_BUS.format(v="1.1.0"), {"bus.sv": "package bus;\nendpackage\n"}),
            _core(
                _CONSUMER.format(n="fifo", c="^1.0.0"),
                {"fifo.sv": "module fifo; import bus::*; endmodule\n"},
            ),
        ]
        plan = plan_package_mangling(cores)
        assert plan.renamed == {}
        assert "import bus::*;" in plan.rewritten[("acme:ip:fifo:1.0.0", "fifo.sv")]

    def test_refuses_colliding_modules(self) -> None:
        cores = [
            _core(_BUS.format(v="1.0.0"), {"m.sv": "module bus; endmodule\n"}),
            _core(_BUS.format(v="2.0.0"), {"m.sv": "module bus; endmodule\n"}),
        ]
        with pytest.raises(BackendError, match="colliding module/entity"):
            plan_package_mangling(cores)

    def test_refuses_unknown_language(self) -> None:
        cores = [
            _core(_BUS.format(v="1.0.0"), {"bus.x": "anything\n"}, language="chiselsource"),
            _core(_BUS.format(v="2.0.0"), {"bus.x": "anything\n"}, language="chiselsource"),
        ]
        with pytest.raises(BackendError, match="language the package mangler does not handle"):
            plan_package_mangling(cores)


class TestVhdlPlanner:
    def _scenario(self) -> list[GenCore]:
        pkg = "package bus is\n  constant W : integer := {w};\nend package bus;\n"
        return [
            _core(_BUS.format(v="1.1.0"), {"bus.vhd": pkg.format(w=8)}, language="vhdl"),
            _core(_BUS.format(v="2.0.0"), {"bus.vhd": pkg.format(w=32)}, language="vhdl"),
            _core(
                _CONSUMER.format(n="fifo", c="^1.0.0"),
                {"fifo.vhd": "use work.bus.all;\nentity fifo is end;\n"},
                language="vhdl",
            ),
            _core(
                _CONSUMER.format(n="legacy", c="^2.0.0"),
                {"legacy.vhd": "use work.bus.all;\nentity legacy is end;\n"},
                language="vhdl",
            ),
        ]

    def test_mangles_vhdl_packages_and_routes_consumers(self) -> None:
        plan = plan_package_mangling(self._scenario())
        assert plan.renamed == {"bus": ("bus__v1_1_0", "bus__v2_0_0")}
        assert "package bus__v1_1_0 is" in plan.rewritten[("acme:common:bus:1.1.0", "bus.vhd")]
        assert "package bus__v2_0_0 is" in plan.rewritten[("acme:common:bus:2.0.0", "bus.vhd")]
        assert "use work.bus__v1_1_0.all;" in plan.rewritten[("acme:ip:fifo:1.0.0", "fifo.vhd")]
        assert "use work.bus__v2_0_0.all;" in plan.rewritten[("acme:ip:legacy:1.0.0", "legacy.vhd")]

    def test_refuses_colliding_vhdl_entities(self) -> None:
        ent = "entity bus is end entity bus;\n"
        cores = [
            _core(_BUS.format(v="1.0.0"), {"e.vhd": ent}, language="vhdl"),
            _core(_BUS.format(v="2.0.0"), {"e.vhd": ent}, language="vhdl"),
        ]
        with pytest.raises(BackendError, match="colliding module/entity"):
            plan_package_mangling(cores)
