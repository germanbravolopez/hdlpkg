"""Unit tests for IP-XACT (IEEE 1685-2014) export (pure: manifest -> XML string)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from hdlpkg.ipxact import IPXACT_NAMESPACE, to_ipxact
from hdlpkg.manifest import Manifest

pytestmark = pytest.mark.unit

NS = {"ipxact": IPXACT_NAMESPACE}

UART = """\
[package]
vendor = "acme"
library = "comm"
name = "uart"
version = "1.2.0"
description = "An example UART"
top = "uart_top"

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
"""


def _root(toml: str) -> ET.Element:
    return ET.fromstring(to_ipxact(Manifest.from_str(toml)))


def test_output_is_well_formed_and_namespaced() -> None:
    root = _root(UART)
    assert root.tag == f"{{{IPXACT_NAMESPACE}}}component"


def test_vlnv_elements() -> None:
    root = _root(UART)
    assert root.findtext("ipxact:vendor", namespaces=NS) == "acme"
    assert root.findtext("ipxact:library", namespaces=NS) == "comm"
    assert root.findtext("ipxact:name", namespaces=NS) == "uart"
    assert root.findtext("ipxact:version", namespaces=NS) == "1.2.0"


def test_filesets_carry_files_and_filetype() -> None:
    root = _root(UART)
    filesets = root.findall(".//ipxact:fileSet", NS)
    names = [fs.findtext("ipxact:name", namespaces=NS) for fs in filesets]
    assert names == ["rtl", "tb"]
    rtl_files = filesets[0].findall("ipxact:file", NS)
    assert [f.findtext("ipxact:name", namespaces=NS) for f in rtl_files] == [
        "rtl/uart_top.sv",
        "rtl/uart_rx.sv",
    ]
    assert rtl_files[0].findtext("ipxact:fileType", namespaces=NS) == "systemVerilogSource"


def test_model_has_a_view_and_instantiation_per_target() -> None:
    root = _root(UART)
    views = root.findall(".//ipxact:view", NS)
    assert [v.findtext("ipxact:name", namespaces=NS) for v in views] == ["sim"]
    inst = root.find(".//ipxact:componentInstantiation", NS)
    assert inst is not None
    assert inst.findtext("ipxact:moduleName", namespaces=NS) == "uart_tb"  # target top wins
    refs = [
        r.findtext("ipxact:localName", namespaces=NS) for r in inst.findall("ipxact:fileSetRef", NS)
    ]
    assert refs == ["rtl", "tb"]


def test_description_is_included() -> None:
    root = _root(UART)
    assert root.findtext("ipxact:description", namespaces=NS) == "An example UART"


def test_export_is_deterministic() -> None:
    manifest = Manifest.from_str(UART)
    assert to_ipxact(manifest) == to_ipxact(manifest)


def test_minimal_manifest_without_targets_or_filesets() -> None:
    minimal = '[package]\nvendor="a"\nlibrary="b"\nname="c"\nversion="0.1.0"\n'
    root = _root(minimal)
    assert root.findtext("ipxact:name", namespaces=NS) == "c"
    assert root.find(".//ipxact:model", NS) is None
    assert root.find(".//ipxact:fileSets", NS) is None
