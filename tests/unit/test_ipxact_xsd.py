"""Validate ``to_ipxact`` output against the official Accellera IP-XACT 1685-2014 XSD.

The schema set is vendored under ``tests/schema/ipxact-1685-2014/`` (see its ``NOTICE``).
These tests prove the exporter emits **schema-valid** IP-XACT -- not merely well-formed
XML -- for the example cores and for custom ``fileType`` values, and that the validator
genuinely rejects non-conformant XML (so the positive assertions mean something).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hdlpkg.ipxact import to_ipxact
from hdlpkg.manifest import Manifest

lxml_etree = pytest.importorskip("lxml.etree", reason="lxml is required to validate XSD")

_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = _ROOT / "tests" / "schema" / "ipxact-1685-2014" / "index.xsd"
_EXAMPLES = _ROOT / "examples"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(not _SCHEMA.is_file(), reason="vendored IP-XACT XSD not present"),
]


@pytest.fixture(scope="module")
def schema() -> object:
    return lxml_etree.XMLSchema(lxml_etree.parse(str(_SCHEMA)))


def _validate(schema: Any, xml: str) -> bool:
    return bool(schema.validate(lxml_etree.fromstring(xml.encode())))


@pytest.mark.parametrize("core", ["fifo", "uart"])
def test_example_cores_validate_against_xsd(schema: Any, core: str) -> None:
    xml = to_ipxact(Manifest.from_path(_EXAMPLES / core / "ip.toml"))
    assert _validate(schema, xml), str(schema.error_log)


_BASE = '[package]\nvendor="v"\nlibrary="l"\nname="n"\nversion="1.0.0"\n'


@pytest.mark.parametrize(
    "manifest_text",
    [
        _BASE,  # VLNV only
        _BASE + '[filesets.r]\nfiles=["a.sv"]\ntype="systemVerilogSource"\n',
        # A non-enum type (custom, or a non-1685-2014 variant) must still validate.
        _BASE + '[filesets.g]\nfiles=["build.tcl"]\ntype="myCustomType"\n',
        _BASE + '[filesets.r]\nfiles=["a.vhd"]\ntype="vhdlSource-2008"\n',
        _BASE + '[filesets.r]\nfiles=["x.bin"]\ntype="user"\n',
    ],
)
def test_custom_file_types_validate(schema: Any, manifest_text: str) -> None:
    assert _validate(schema, to_ipxact(Manifest.from_str(manifest_text)))


def test_custom_type_uses_the_user_escape(schema: Any) -> None:
    xml = to_ipxact(Manifest.from_str(_BASE + '[filesets.g]\nfiles=["b"]\ntype="weirdType"\n'))
    # The non-enum type rides in the ``user`` attribute, with element text "user".
    assert 'user="weirdType"' in xml
    assert _validate(schema, xml)


def test_validator_rejects_non_conformant_xml(schema: Any) -> None:
    # The pre-fix output (a raw non-enum fileType) must fail -- proves the guard works.
    ns = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"
    bad = (
        f'<ipxact:component xmlns:ipxact="{ns}">'
        "<ipxact:vendor>v</ipxact:vendor><ipxact:library>l</ipxact:library>"
        "<ipxact:name>n</ipxact:name><ipxact:version>1.0.0</ipxact:version>"
        "<ipxact:fileSets><ipxact:fileSet><ipxact:name>s</ipxact:name>"
        "<ipxact:file><ipxact:name>x</ipxact:name>"
        "<ipxact:fileType>myCustomType</ipxact:fileType>"
        "</ipxact:file></ipxact:fileSet></ipxact:fileSets></ipxact:component>"
    )
    assert not _validate(schema, bad)
