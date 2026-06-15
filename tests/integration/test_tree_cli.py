"""Integration test: ``hdlpkg tree`` over the bundled examples."""

from __future__ import annotations

from pathlib import Path

import pytest

from hdlpkg import cli

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
UART_MANIFEST = EXAMPLES / "uart" / "ip.toml"


def test_tree_shows_root_and_resolved_dependency(capsys) -> None:
    rc = cli.main(["tree", str(UART_MANIFEST), "--search", str(EXAMPLES)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "acme:comm:uart:1.2.0"
    assert "acme:common:fifo" in out
    assert "-> 1.0.0" in out
