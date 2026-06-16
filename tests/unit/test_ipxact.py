"""Unit tests for IP-XACT (IEEE 1685-2014) export (pure: manifest -> XML string)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from hdlpkg.ipxact import IPXACT_NAMESPACE, IPXACT_NAMESPACES, to_ipxact
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


# --- IP-XACT 2022 output mode --------------------------------------------------------

NS22 = {"ipxact": IPXACT_NAMESPACES["2022"]}


def test_2022_uses_the_2022_namespace() -> None:
    root = ET.fromstring(to_ipxact(Manifest.from_str(UART), std="2022"))
    assert root.tag == f"{{{IPXACT_NAMESPACES['2022']}}}component"


def _local_tags(root: ET.Element) -> list[str]:
    return [child.tag.rsplit("}", 1)[-1] for child in root]


def test_2022_places_description_right_after_version() -> None:
    # 2022 carries description in the documentNameGroup (after version, before model); 2014
    # trails it after fileSets. Assert the relative position in each.
    tags22 = _local_tags(ET.fromstring(to_ipxact(Manifest.from_str(UART), std="2022")))
    assert tags22.index("description") == tags22.index("version") + 1
    assert tags22.index("description") < tags22.index("model")

    tags14 = _local_tags(ET.fromstring(to_ipxact(Manifest.from_str(UART), std="2014")))
    assert tags14.index("description") > tags14.index("fileSets")


PARAMS = (
    UART + '\n[ipxact.parameters]\nWIDTH = 8\nDEPTH = { value = 16, description = "FIFO depth" }\n'
)


@pytest.mark.parametrize("std", ["2014", "2022"])
def test_parameters_are_emitted(std: str) -> None:
    ns = {"ipxact": IPXACT_NAMESPACES[std]}
    root = ET.fromstring(to_ipxact(Manifest.from_str(PARAMS), std=std))
    params = root.findall(".//ipxact:parameters/ipxact:parameter", ns)
    by_name = {p.findtext("ipxact:name", namespaces=ns): p for p in params}
    assert set(by_name) == {"WIDTH", "DEPTH"}
    assert by_name["WIDTH"].findtext("ipxact:value", namespaces=ns) == "8"
    assert by_name["DEPTH"].findtext("ipxact:value", namespaces=ns) == "16"
    assert by_name["DEPTH"].findtext("ipxact:description", namespaces=ns) == "FIFO depth"


def test_no_parameters_section_when_absent() -> None:
    root = _root(UART)  # UART declares no [ipxact.parameters]
    assert root.find(".//ipxact:parameters", NS) is None


def test_2022_keeps_vlnv_and_filesets() -> None:
    root = ET.fromstring(to_ipxact(Manifest.from_str(UART), std="2022"))
    assert root.findtext("ipxact:name", namespaces=NS22) == "uart"
    names = [
        fs.findtext("ipxact:name", namespaces=NS22)
        for fs in root.findall(".//ipxact:fileSet", NS22)
    ]
    assert names == ["rtl", "tb"]
    assert root.find(".//ipxact:model", NS) is None
    assert root.find(".//ipxact:fileSets", NS) is None
