"""Unit tests for CycloneDX SBOM generation (pure: manifests -> JSON string)."""

from __future__ import annotations

import json

import pytest

from hdlpkg.manifest import Manifest
from hdlpkg.sbom import CYCLONEDX_SPEC_VERSION, build_cyclonedx

pytestmark = pytest.mark.unit

FIFO = """\
[package]
vendor = "acme"
library = "common"
name = "fifo"
version = "1.0.0"
license = "Apache-2.0"
"""

UART = """\
[package]
vendor = "acme"
library = "comm"
name = "uart"
version = "1.2.0"
description = "An example UART"
license = "Apache-2.0"
[dependencies]
"acme:common:fifo" = "^1.0.0"
"""


def _bom(root: str, deps: list[str] | None = None) -> dict:
    manifests = [Manifest.from_str(d) for d in (deps or [])]
    return json.loads(build_cyclonedx(Manifest.from_str(root), manifests))


def test_envelope_fields() -> None:
    bom = _bom(UART, [FIFO])
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == CYCLONEDX_SPEC_VERSION
    assert bom["version"] == 1


def test_root_is_the_metadata_component() -> None:
    bom = _bom(UART, [FIFO])
    comp = bom["metadata"]["component"]
    assert comp["bom-ref"] == "acme:comm:uart:1.2.0"
    assert comp["name"] == "uart"
    assert comp["group"] == "acme.comm"
    assert comp["version"] == "1.2.0"
    assert comp["purl"] == "pkg:generic/acme.comm/uart@1.2.0"
    assert comp["description"] == "An example UART"
    assert comp["licenses"] == [{"license": {"id": "Apache-2.0"}}]


def test_dependencies_become_components_and_edges() -> None:
    bom = _bom(UART, [FIFO])
    refs = [c["bom-ref"] for c in bom["components"]]
    assert refs == ["acme:common:fifo:1.0.0"]
    assert bom["dependencies"] == [
        {"ref": "acme:comm:uart:1.2.0", "dependsOn": ["acme:common:fifo:1.0.0"]}
    ]


def test_leaf_core_has_no_components_or_edges() -> None:
    bom = _bom(FIFO)
    assert bom["components"] == []
    assert bom["dependencies"] == []
    assert bom["metadata"]["component"]["bom-ref"] == "acme:common:fifo:1.0.0"


def test_output_is_deterministic() -> None:
    root = Manifest.from_str(UART)
    deps = [Manifest.from_str(FIFO)]
    assert build_cyclonedx(root, deps) == build_cyclonedx(root, deps)
