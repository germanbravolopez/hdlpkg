"""Unit tests for the SystemVerilog package mangler (pure, no I/O).

Covers the comment/string-aware rewriter (only unambiguous package positions are
touched), the declaration scanners, and the multi-version planner (rename maps,
per-consumer resolution, and the refusals for module collisions / VHDL).
"""

from __future__ import annotations

import pytest

from hdlpkg.exceptions import BackendError
from hdlpkg.mangle import (
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
from hdlpkg.manifest import Manifest
from hdlpkg.version import Version

pytestmark = pytest.mark.unit


class TestScanners:
    def test_declared_packages(self) -> None:
        src = "// package not_this\npackage bus_pkg;\nendpackage : bus_pkg\n"
        assert declared_packages(src) == ("bus_pkg",)

    def test_declared_modules_and_interfaces(self) -> None:
        src = "module top; endmodule\ninterface bus_if; endinterface\n"
        assert set(declared_modules(src)) == {"top", "bus_if"}

    def test_mangled_name_is_sv_and_vhdl_safe(self) -> None:
        assert mangled_name("bus_pkg", Version.parse("1.1.0")) == "bus_pkg_v1_1_0"
        assert mangled_name("p", Version.parse("2.0.0-rc.1")) == "p_v2_0_0_rc_1"

    def test_mangled_name_never_has_consecutive_underscores(self) -> None:
        # VHDL forbids consecutive underscores in an identifier; a name that itself
        # ends in '_' (or any input that would butt underscores together) must still
        # produce a legal identifier, not 'foo__v1_0_0'.
        for name in ("foo", "foo_", "bus_pkg"):
            for spec in ("1.0.0", "2.0.0-rc.1", "1.0.0+build.5"):
                result = mangled_name(name, Version.parse(spec))
                assert "__" not in result, result
                assert not result.startswith("_") and not result.endswith("_"), result


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
        assert plan.renamed == {"bus": ("bus_v1_1_0", "bus_v2_0_0")}
        # each package version keeps its own mangled name
        assert "package bus_v1_1_0;" in plan.rewritten[("acme:common:bus:1.1.0", "bus.sv")]
        assert "package bus_v2_0_0;" in plan.rewritten[("acme:common:bus:2.0.0", "bus.sv")]
        # each consumer is routed to the version it resolved to
        assert "import bus_v1_1_0::*;" in plan.rewritten[("acme:ip:fifo:1.0.0", "fifo.sv")]
        assert "import bus_v2_0_0::*;" in plan.rewritten[("acme:ip:legacy:1.0.0", "legacy.sv")]

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

    def test_refuses_when_two_versions_mangle_to_the_same_name(self) -> None:
        # Two opaque versions differing only by a separator run flatten to one HDL-safe
        # name (1.0 / 1..0 -> bus_v1_0); the planner must refuse, not silently collide.
        opaque = (
            '[package]\nvendor="acme"\nlibrary="common"\nname="bus"\n'
            'scheme = "opaque"\nversion = "{v}"\n'
        )
        cores = [
            _core(opaque.format(v="1.0"), {"bus.sv": "package bus;\nendpackage\n"}),
            _core(opaque.format(v="1..0"), {"bus.sv": "package bus;\nendpackage\n"}),
        ]
        with pytest.raises(BackendError, match="mangled names collide"):
            plan_package_mangling(cores)

    def _module_scenario(self, consumer_body: str) -> list[GenCore]:
        # Two versions of a `module bus` collide; one consumer (resolving to ^1.0.0)
        # instantiates it via *consumer_body*.
        return [
            _core(_BUS.format(v="1.0.0"), {"bus.sv": "module bus; endmodule\n"}),
            _core(_BUS.format(v="2.0.0"), {"bus.sv": "module bus; endmodule\n"}),
            _core(_CONSUMER.format(n="fifo", c="^1.0.0"), {"fifo.sv": consumer_body}),
        ]

    def test_mangles_coexisting_modules_and_routes_instantiations(self) -> None:
        cores = [
            _core(_BUS.format(v="1.0.0"), {"bus.sv": "module bus; endmodule\n"}),
            _core(_BUS.format(v="2.0.0"), {"bus.sv": "module bus; endmodule\n"}),
            _core(
                _CONSUMER.format(n="fifo", c="^1.0.0"),
                {"fifo.sv": "module fifo; bus u_bus (); endmodule\n"},
            ),
            _core(
                _CONSUMER.format(n="legacy", c="^2.0.0"),
                {"legacy.sv": "module legacy; bus u_bus (); endmodule\n"},
            ),
        ]
        plan = plan_package_mangling(cores)
        assert plan.renamed == {"bus": ("bus_v1_0_0", "bus_v2_0_0")}
        assert "module bus_v1_0_0;" in plan.rewritten[("acme:common:bus:1.0.0", "bus.sv")]
        assert "module bus_v2_0_0;" in plan.rewritten[("acme:common:bus:2.0.0", "bus.sv")]
        # each consumer's instantiation routed to the version it resolved to
        assert "bus_v1_0_0 u_bus ()" in plan.rewritten[("acme:ip:fifo:1.0.0", "fifo.sv")]
        assert "bus_v2_0_0 u_bus ()" in plan.rewritten[("acme:ip:legacy:1.0.0", "legacy.sv")]

    def test_mangles_instantiation_variants_and_generate(self) -> None:
        body = (
            "module fifo;\n"
            "  bus u0 ();\n"  # plain
            "  bus #(.W(8)) u1 ();\n"  # parameter map
            "  bus u2 [3:0] ();\n"  # instance array
            "  bus a (), b ();\n"  # multiple instances
            "  generate for (genvar i=0;i<2;i=i+1) begin : g bus g0 (); end endgenerate\n"
            "endmodule\n"
        )
        out = plan_package_mangling(self._module_scenario(body)).rewritten[
            ("acme:ip:fifo:1.0.0", "fifo.sv")
        ]
        assert "bus_v1_0_0 u0 ()" in out
        assert "bus_v1_0_0 #(.W(8)) u1 ()" in out
        assert "bus_v1_0_0 u2 [3:0] ()" in out
        assert "bus_v1_0_0 a (), b ()" in out
        assert "begin : g bus_v1_0_0 g0 ()" in out  # generate-nested instance
        assert "bus " not in out.replace("bus_v1_0_0", "")  # no bare 'bus' left

    def test_leaves_inert_module_name_occurrences(self) -> None:
        # A coincidental value/member use of the name is inert (not rewritten, not refused).
        body = "module fifo;\n  logic bus;\n  assign bus = top.bus;\n  bus u ();\nendmodule\n"
        out = plan_package_mangling(self._module_scenario(body)).rewritten[
            ("acme:ip:fifo:1.0.0", "fifo.sv")
        ]
        assert "logic bus;" in out  # signal decl untouched
        assert "assign bus = top.bus;" in out  # value + hierarchical member untouched
        assert "bus_v1_0_0 u ()" in out  # the real instantiation rewritten

    def test_refuses_unclassifiable_module_occurrence(self) -> None:
        # `bus inst;` (a would-be variable of module type) is neither a declaration, an
        # instantiation, nor inert -> refuse rather than risk a dangling reference.
        body = "module fifo;\n  bus inst;\nendmodule\n"
        with pytest.raises(BackendError, match="cannot classify"):
            plan_package_mangling(self._module_scenario(body))

    def test_refuses_module_param_map_without_instance(self) -> None:
        # `bus #(.W(8));` has a param map but no instance name -> not a matched instantiation
        # shape; the `#` must trigger a refusal, not be mistaken for an inert value.
        body = "module fifo;\n  bus #(.W(8));\nendmodule\n"
        with pytest.raises(BackendError, match="cannot classify"):
            plan_package_mangling(self._module_scenario(body))

    def test_refuses_name_colliding_under_two_kinds(self) -> None:
        # One name colliding as both a module (ref a:x) and an interface (ref b:y) cannot be
        # mangled with a single kind -> refuse rather than mis-rewrite one set of positions.
        mod = '[package]\nvendor="acme"\nlibrary="a"\nname="x"\nversion="{v}"\n'
        ifc = '[package]\nvendor="acme"\nlibrary="b"\nname="y"\nversion="{v}"\n'
        cores = [
            _core(mod.format(v="1.0.0"), {"m.sv": "module foo; endmodule\n"}),
            _core(mod.format(v="2.0.0"), {"m.sv": "module foo; endmodule\n"}),
            _core(ifc.format(v="1.0.0"), {"i.sv": "interface foo; endinterface\n"}),
            _core(ifc.format(v="2.0.0"), {"i.sv": "interface foo; endinterface\n"}),
        ]
        with pytest.raises(BackendError, match="collides as both"):
            plan_package_mangling(cores)

    def _interface_scenario(self, consumer_body: str) -> list[GenCore]:
        ifc = "interface bus; endinterface\n"
        return [
            _core(_BUS.format(v="1.0.0"), {"bus.sv": ifc}),
            _core(_BUS.format(v="2.0.0"), {"bus.sv": ifc}),
            _core(_CONSUMER.format(n="fifo", c="^1.0.0"), {"fifo.sv": consumer_body}),
        ]

    def test_mangles_coexisting_interfaces_all_positions(self) -> None:
        body = (
            "module fifo (bus port_if, bus.master mp);\n"  # port type + modport select
            "  bus u_if ();\n"  # instantiation
            "  virtual bus v;\n"  # virtual interface
            "endmodule\n"
        )
        plan = plan_package_mangling(self._interface_scenario(body))
        assert plan.renamed == {"bus": ("bus_v1_0_0", "bus_v2_0_0")}
        assert "interface bus_v1_0_0;" in plan.rewritten[("acme:common:bus:1.0.0", "bus.sv")]
        out = plan.rewritten[("acme:ip:fifo:1.0.0", "fifo.sv")]
        assert "module fifo (bus_v1_0_0 port_if, bus_v1_0_0.master mp)" in out
        assert "bus_v1_0_0 u_if ()" in out
        assert "virtual bus_v1_0_0 v;" in out

    def test_refuses_unclassifiable_interface_occurrence(self) -> None:
        # An interface name as a type-parameter default is an unmodeled type context.
        body = "module fifo #(type T = bus) (); endmodule\n"
        with pytest.raises(BackendError, match="cannot classify"):
            plan_package_mangling(self._interface_scenario(body))

    def test_member_access_is_not_mistaken_for_a_modport_select(self) -> None:
        # `bus.flag <= x` is a member access on a coincidentally same-named variable, NOT a
        # modport-type select (`bus.master mp`), so it must not be silently rewritten -- the
        # ambiguous occurrence is refused instead of corrupting `bus.flag`.
        body = "module fifo;\n  logic bus_flag;\n  assign bus_flag = bus.flag;\nendmodule\n"
        with pytest.raises(BackendError, match="cannot classify"):
            plan_package_mangling(self._interface_scenario(body))

    def test_refuses_unknown_language(self) -> None:
        cores = [
            _core(_BUS.format(v="1.0.0"), {"bus.x": "anything\n"}, language="chiselsource"),
            _core(_BUS.format(v="2.0.0"), {"bus.x": "anything\n"}, language="chiselsource"),
        ]
        with pytest.raises(BackendError, match="language the mangler does not handle"):
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
        assert plan.renamed == {"bus": ("bus_v1_1_0", "bus_v2_0_0")}
        assert "package bus_v1_1_0 is" in plan.rewritten[("acme:common:bus:1.1.0", "bus.vhd")]
        assert "package bus_v2_0_0 is" in plan.rewritten[("acme:common:bus:2.0.0", "bus.vhd")]
        assert "use work.bus_v1_1_0.all;" in plan.rewritten[("acme:ip:fifo:1.0.0", "fifo.vhd")]
        assert "use work.bus_v2_0_0.all;" in plan.rewritten[("acme:ip:legacy:1.0.0", "legacy.vhd")]

    def _entity_scenario(self, consumer_body: str) -> list[GenCore]:
        # Two versions of `entity bus`; one consumer (resolving to ^1.0.0) references it.
        ent = "entity bus is end entity bus;\narchitecture rtl of bus is begin end rtl;\n"
        return [
            _core(_BUS.format(v="1.0.0"), {"bus.vhd": ent}, language="vhdl"),
            _core(_BUS.format(v="2.0.0"), {"bus.vhd": ent}, language="vhdl"),
            _core(
                _CONSUMER.format(n="fifo", c="^1.0.0"),
                {"fifo.vhd": consumer_body},
                language="vhdl",
            ),
        ]

    def test_mangles_coexisting_entities_decl_and_arch(self) -> None:
        plan = plan_package_mangling(self._entity_scenario("entity fifo is end;\n"))
        assert plan.renamed == {"bus": ("bus_v1_0_0", "bus_v2_0_0")}
        v1 = plan.rewritten[("acme:common:bus:1.0.0", "bus.vhd")]
        assert "entity bus_v1_0_0 is end entity bus_v1_0_0;" in v1
        assert "architecture rtl of bus_v1_0_0 is" in v1
        assert "entity bus_v2_0_0 is" in plan.rewritten[("acme:common:bus:2.0.0", "bus.vhd")]

    def test_mangles_direct_instantiation(self) -> None:
        body = (
            "architecture rtl of fifo is\nbegin\n"
            "  u : entity work.bus port map (clk => clk);\n"
            "  g : for i in 0 to 1 generate u2 : entity work.bus; end generate;\n"
            "end rtl;\n"
        )
        out = plan_package_mangling(self._entity_scenario(body)).rewritten[
            ("acme:ip:fifo:1.0.0", "fifo.vhd")
        ]
        assert "u : entity work.bus_v1_0_0 port map" in out
        assert "u2 : entity work.bus_v1_0_0;" in out  # generate-nested direct instance

    def test_mangles_component_instantiation(self) -> None:
        body = (
            "architecture rtl of fifo is\n"
            "  component bus port (clk : in bit); end component;\n"
            "begin\n"
            "  u : bus port map (clk => clk);\n"
            "  u3 : component bus port map (clk => clk);\n"
            "end rtl;\n"
        )
        out = plan_package_mangling(self._entity_scenario(body)).rewritten[
            ("acme:ip:fifo:1.0.0", "fifo.vhd")
        ]
        assert "component bus_v1_0_0 port" in out  # component declaration
        assert "u : bus_v1_0_0 port map" in out  # bare component instantiation
        assert "u3 : component bus_v1_0_0 port map" in out

    def test_leaves_label_and_selected_name_inert(self) -> None:
        # `bus :` is a label and `rec.bus` is a selected name -- neither is an entity ref.
        body = (
            "architecture rtl of fifo is\nbegin\n"
            "  bus : process begin end process;\n"  # a label coinciding with the name
            "  u : entity work.bus;\n"  # the real reference
            "end rtl;\n"
        )
        out = plan_package_mangling(self._entity_scenario(body)).rewritten[
            ("acme:ip:fifo:1.0.0", "fifo.vhd")
        ]
        assert "bus : process" in out  # label untouched
        assert "u : entity work.bus_v1_0_0;" in out  # reference rewritten

    def test_refuses_entity_name_declared_by_another_core(self) -> None:
        # The same entity name declared by an unrelated core is ambiguous -> refuse.
        cores = self._entity_scenario("entity bus is end;\n")  # consumer also declares `bus`
        with pytest.raises(BackendError, match="ambiguous across"):
            plan_package_mangling(cores)
