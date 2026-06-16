"""Validate ``to_ipxact`` output against the official Accellera IP-XACT XSDs.

The 1685-2014 and 1685-2022 schema sets are vendored under ``tests/schema/`` (see each
dir's ``NOTICE``). These tests prove the exporter emits **schema-valid** IP-XACT -- not
merely well-formed XML -- for the example cores and for custom ``fileType`` values, in
**both** standards, and that the validator genuinely rejects non-conformant XML (so the
positive assertions mean something).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hdlpkg.ipxact import IPXACT_NAMESPACES, SUPPORTED_IPXACT_STDS, IpxactStd, to_ipxact
from hdlpkg.manifest import Manifest

lxml_etree = pytest.importorskip("lxml.etree", reason="lxml is required to validate XSD")

_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES = _ROOT / "examples"


def _schema_path(std: IpxactStd) -> Path:
    return _ROOT / "tests" / "schema" / f"ipxact-1685-{std}" / "index.xsd"


pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not all(_schema_path(std).is_file() for std in SUPPORTED_IPXACT_STDS),
        reason="vendored IP-XACT XSD not present",
    ),
]


@pytest.fixture(scope="module", params=SUPPORTED_IPXACT_STDS)
def std_schema(request: Any) -> tuple[IpxactStd, Any]:
    """A (standard, compiled-XSD) pair for each supported IP-XACT revision."""
    std: IpxactStd = request.param
    schema = lxml_etree.XMLSchema(lxml_etree.parse(str(_schema_path(std))))
    return std, schema


def _validate(schema: Any, xml: str) -> bool:
    return bool(schema.validate(lxml_etree.fromstring(xml.encode())))


@pytest.mark.parametrize("core", ["fifo", "uart"])
def test_example_cores_validate_against_xsd(std_schema: tuple[IpxactStd, Any], core: str) -> None:
    std, schema = std_schema
    xml = to_ipxact(Manifest.from_path(_EXAMPLES / core / "ip.toml"), std=std)
    assert _validate(schema, xml), str(schema.error_log)


def test_output_carries_the_requested_standard_namespace(
    std_schema: tuple[IpxactStd, Any],
) -> None:
    std, _ = std_schema
    xml = to_ipxact(Manifest.from_path(_EXAMPLES / "uart" / "ip.toml"), std=std)
    assert IPXACT_NAMESPACES[std] in xml


_BASE = '[package]\nvendor="v"\nlibrary="l"\nname="n"\nversion="1.0.0"\n'


@pytest.mark.parametrize(
    "manifest_text",
    [
        _BASE,  # VLNV only
        _BASE + '[filesets.r]\nfiles=["a.sv"]\ntype="systemVerilogSource"\n',
        # A non-enum type (custom, or a non-enumerated variant) must still validate.
        _BASE + '[filesets.g]\nfiles=["build.tcl"]\ntype="myCustomType"\n',
        _BASE + '[filesets.r]\nfiles=["a.vhd"]\ntype="vhdlSource-2008"\n',
        _BASE + '[filesets.r]\nfiles=["x.bin"]\ntype="user"\n',
    ],
)
def test_custom_file_types_validate(std_schema: tuple[IpxactStd, Any], manifest_text: str) -> None:
    std, schema = std_schema
    assert _validate(schema, to_ipxact(Manifest.from_str(manifest_text), std=std))


def test_description_validates_in_both_standards(std_schema: tuple[IpxactStd, Any]) -> None:
    # 2014 trails description after fileSets; 2022 carries it in documentNameGroup. Both
    # must validate with a description present (and filesets, to exercise the ordering).
    std, schema = std_schema
    text = (
        _BASE
        + 'description="My core"\n'
        + '[filesets.r]\nfiles=["a.sv"]\ntype="systemVerilogSource"\n'
    )
    xml = to_ipxact(Manifest.from_str(text), std=std)
    assert "My core" in xml
    assert _validate(schema, xml), str(schema.error_log)


def test_custom_type_uses_the_user_escape(std_schema: tuple[IpxactStd, Any]) -> None:
    std, schema = std_schema
    xml = to_ipxact(
        Manifest.from_str(_BASE + '[filesets.g]\nfiles=["b"]\ntype="weirdType"\n'), std=std
    )
    # The non-enum type rides in the ``user`` attribute, with element text "user".
    assert 'user="weirdType"' in xml
    assert _validate(schema, xml)


@pytest.mark.parametrize("std", SUPPORTED_IPXACT_STDS)
def test_validator_rejects_non_conformant_xml(std: IpxactStd) -> None:
    # A raw non-enum fileType must fail -- proves the guard (and the validator) work.
    schema = lxml_etree.XMLSchema(lxml_etree.parse(str(_schema_path(std))))
    ns = IPXACT_NAMESPACES[std]
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
