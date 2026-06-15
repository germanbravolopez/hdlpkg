"""Integration test: ``hdlpkg pack --sbom`` over the bundled examples."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hdlpkg import cli

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
UART_MANIFEST = EXAMPLES / "uart" / "ip.toml"


def test_pack_sbom_includes_resolved_dependency(tmp_path: Path, capsys) -> None:
    ipkg = tmp_path / "uart.ipkg"
    sbom = tmp_path / "uart.cdx.json"
    rc = cli.main(
        [
            "pack",
            str(UART_MANIFEST),
            "--output",
            str(ipkg),
            "--sbom",
            str(sbom),
            "--search",
            str(EXAMPLES),
        ]
    )
    assert rc == 0
    assert ipkg.is_file()
    out = capsys.readouterr().out
    assert "Wrote SBOM" in out

    bom = json.loads(sbom.read_text(encoding="utf-8"))
    assert bom["metadata"]["component"]["bom-ref"] == "acme:comm:uart:1.2.0"
    assert [c["bom-ref"] for c in bom["components"]] == ["acme:common:fifo:1.0.0"]
