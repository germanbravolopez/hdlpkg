"""Unit tests for hdl_ip_packager.manifest (ip.toml parsing + validation)."""

from __future__ import annotations

import pytest

from hdl_ip_packager.exceptions import ManifestError
from hdl_ip_packager.manifest import Manifest
from hdl_ip_packager.version import Version

pytestmark = pytest.mark.unit


class TestManifestHappyPath:
    def test_parses_identity(self, sample_manifest_toml: str) -> None:
        m = Manifest.from_str(sample_manifest_toml)
        assert str(m.vlnv) == "acme:comm:uart:1.2.0"
        assert m.vlnv.version == Version.parse("1.2.0")
        assert m.description.startswith("AXI-Lite UART")
        assert m.license == "Apache-2.0"
        assert m.authors == ("Jane Doe <jane@acme.com>",)
        assert m.top == "uart_top"
        assert m.keywords == ("uart", "axi", "serial")

    def test_parses_dependencies(self, sample_manifest_toml: str) -> None:
        m = Manifest.from_str(sample_manifest_toml)
        deps = {str(d.ref): d for d in m.dependencies}
        assert set(deps) == {"acme:common:fifo", "vendorx:axi:axil_bfm"}
        assert deps["acme:common:fifo"].constraint.matches(Version.parse("1.4.0"))
        assert not deps["acme:common:fifo"].constraint.matches(Version.parse("2.0.0"))
        assert deps["vendorx:axi:axil_bfm"].constraint.matches(Version.parse("2.5.0"))

    def test_parses_filesets(self, sample_manifest_toml: str) -> None:
        m = Manifest.from_str(sample_manifest_toml)
        assert set(m.filesets) == {"rtl", "tb"}
        assert m.filesets["rtl"].files == ("rtl/uart_top.sv", "rtl/uart_fifo.sv")
        assert m.filesets["rtl"].type == "systemVerilogSource"
        assert m.filesets["tb"].depend == ("dev",)

    def test_parses_targets(self, sample_manifest_toml: str) -> None:
        m = Manifest.from_str(sample_manifest_toml)
        assert set(m.targets) == {"sim", "synth"}
        assert m.targets["sim"].toolflow == "verilator"
        assert m.targets["sim"].filesets == ("rtl", "tb")
        assert m.targets["sim"].top == "uart_tb"
        assert m.targets["synth"].top is None

    def test_from_path(self, write_manifest) -> None:
        path = write_manifest()
        m = Manifest.from_path(path)
        assert str(m.vlnv) == "acme:comm:uart:1.2.0"
        assert m.ref == m.vlnv.ref

    def test_minimal_manifest(self) -> None:
        m = Manifest.from_str('[package]\nvendor="a"\nlibrary="b"\nname="c"\nversion="0.1.0"\n')
        assert str(m.vlnv) == "a:b:c:0.1.0"
        assert m.dependencies == ()
        assert m.filesets == {}
        assert m.targets == {}


class TestManifestErrors:
    def test_missing_package_table(self) -> None:
        with pytest.raises(ManifestError, match="package"):
            Manifest.from_str('[dependencies]\n"a:b:c" = "*"\n')

    def test_missing_required_version(self) -> None:
        with pytest.raises(ManifestError, match="version"):
            Manifest.from_str('[package]\nvendor="a"\nlibrary="b"\nname="c"\n')

    def test_invalid_version(self) -> None:
        with pytest.raises(ManifestError):
            Manifest.from_str('[package]\nvendor="a"\nlibrary="b"\nname="c"\nversion="1.2"\n')

    def test_invalid_toml(self) -> None:
        with pytest.raises(ManifestError, match="Invalid TOML"):
            Manifest.from_str("this is = = not toml")

    def test_dependency_value_not_string(self) -> None:
        toml = (
            '[package]\nvendor="a"\nlibrary="b"\nname="c"\nversion="0.1.0"\n'
            "[dependencies]\n"
            '"x:y:z" = 123\n'
        )
        with pytest.raises(ManifestError, match="constraint string"):
            Manifest.from_str(toml)

    def test_bad_dependency_constraint(self) -> None:
        toml = (
            '[package]\nvendor="a"\nlibrary="b"\nname="c"\nversion="0.1.0"\n'
            "[dependencies]\n"
            '"x:y:z" = ">="\n'
        )
        with pytest.raises(ManifestError, match="Invalid dependency"):
            Manifest.from_str(toml)

    def test_target_references_unknown_fileset(self) -> None:
        toml = (
            '[package]\nvendor="a"\nlibrary="b"\nname="c"\nversion="0.1.0"\n'
            "[targets.sim]\ntoolflow='verilator'\nfilesets=['nope']\n"
        )
        with pytest.raises(ManifestError, match="unknown fileset"):
            Manifest.from_str(toml)

    def test_fileset_missing_files(self) -> None:
        toml = (
            '[package]\nvendor="a"\nlibrary="b"\nname="c"\nversion="0.1.0"\n'
            "[filesets.rtl]\ntype='systemVerilogSource'\n"
        )
        with pytest.raises(ManifestError, match="files"):
            Manifest.from_str(toml)

    def test_from_path_missing_file(self, tmp_path) -> None:
        with pytest.raises(ManifestError, match="Cannot read"):
            Manifest.from_path(tmp_path / "does_not_exist.toml")


_MINIMAL = '[package]\nvendor="a"\nlibrary="b"\nname="c"\nversion="0.1.0"\n'


class TestManifestSchemaVersion:
    def test_absent_schema_defaults_to_1(self) -> None:
        assert Manifest.from_str(_MINIMAL).schema_version == 1

    def test_explicit_schema_1_parses(self) -> None:
        assert Manifest.from_str("schema = 1\n" + _MINIMAL).schema_version == 1

    def test_future_schema_is_rejected(self) -> None:
        with pytest.raises(ManifestError, match="schema version 2"):
            Manifest.from_str("schema = 2\n" + _MINIMAL)

    def test_non_integer_schema_is_rejected(self) -> None:
        with pytest.raises(ManifestError, match="'schema' must be an integer"):
            Manifest.from_str('schema = "1"\n' + _MINIMAL)
