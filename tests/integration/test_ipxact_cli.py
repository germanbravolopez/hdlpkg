"""Integration test: ``hdlpkg export-ipxact`` over a bundled example."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from hdlpkg import cli
from hdlpkg.ipxact import IPXACT_NAMESPACE

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
UART_MANIFEST = EXAMPLES / "uart" / "ip.toml"
NS = {"ipxact": IPXACT_NAMESPACE}


def test_export_ipxact_writes_a_valid_component(tmp_path: Path, capsys) -> None:
    out = tmp_path / "uart.xml"
    rc = cli.main(["export-ipxact", str(UART_MANIFEST), "--output", str(out)])
    assert rc == 0
    assert "Exported IP-XACT" in capsys.readouterr().out

    root = ET.parse(out).getroot()
    assert root.tag == f"{{{IPXACT_NAMESPACE}}}component"
    assert root.findtext("ipxact:name", namespaces=NS) == "uart"
    assert root.findtext("ipxact:version", namespaces=NS) == "1.2.0"
    fileset_names = [
        fs.findtext("ipxact:name", namespaces=NS) for fs in root.findall(".//ipxact:fileSet", NS)
    ]
    assert "rtl" in fileset_names
