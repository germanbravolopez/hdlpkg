"""Shared pytest fixtures and a local per-module summary for the whole suite.

This file is auto-discovered by pytest and applies to every test under ``tests/``.
Two things live here:

1. Reusable fixtures (sample manifests, a manifest-writing factory) so individual
   test modules stay short and focused.
2. A ``pytest_terminal_summary`` hook that prints a compact pass/fail table grouped
   by test module at the end of every *local* run - the same information the CI
   step summary shows, available without leaving the terminal.

Keeping fixtures and reporting here is what lets the suite scale: a new test
module just imports nothing extra and immediately gets the fixtures and the
summary.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

# A complete, valid manifest used across manifest/CLI tests. Keep it in sync with
# the schema documented in src/hdl_ip_packager/manifest.py.
SAMPLE_MANIFEST = """\
[package]
vendor      = "acme"
library     = "comm"
name        = "uart"
version     = "1.2.0"
description = "AXI-Lite UART with configurable FIFOs"
license     = "Apache-2.0"
authors     = ["Jane Doe <jane@acme.com>"]
top         = "uart_top"
keywords    = ["uart", "axi", "serial"]

[dependencies]
"acme:common:fifo"     = "^1.0.0"
"vendorx:axi:axil_bfm" = ">=2.1.0,<3.0.0"

[filesets.rtl]
files = ["rtl/uart_top.sv", "rtl/uart_fifo.sv"]
type  = "systemVerilogSource"

[filesets.tb]
files  = ["tb/uart_tb.sv"]
type   = "systemVerilogSource"
depend = ["dev"]

[targets.sim]
toolflow = "verilator"
filesets = ["rtl", "tb"]
top      = "uart_tb"

[targets.synth]
toolflow = "vivado"
filesets = ["rtl"]
"""


@pytest.fixture
def sample_manifest_toml() -> str:
    """The canonical valid manifest as a TOML string."""
    return SAMPLE_MANIFEST


@pytest.fixture
def write_manifest(tmp_path: Path):
    """Factory: write a manifest string to a temp ``ip.toml`` and return its path."""

    def _write(text: str = SAMPLE_MANIFEST, name: str = "ip.toml") -> Path:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    return _write


# --------------------------------------------------------------------------- #
# Local terminal summary: a per-module pass/fail table at the end of the run.   #
# --------------------------------------------------------------------------- #
def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    tr = terminalreporter
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    )
    for status in ("passed", "failed", "error", "skipped"):
        for rep in tr.stats.get(status, []):
            when = getattr(rep, "when", None)
            # Count a test once, on its call phase; setup/teardown failures and
            # skips still surface because they carry when='setup'/'call'.
            if status == "passed" and when != "call":
                continue
            if status == "skipped" and when not in ("setup", "call"):
                continue
            module = getattr(rep, "nodeid", "?").split("::")[0]
            counts[module][status] += 1

    if not counts:
        return

    tr.write_sep("=", "summary by module")
    name_width = max((len(m) for m in counts), default=10)
    for module in sorted(counts):
        c = counts[module]
        total = sum(c.values())
        ok = c["failed"] == 0 and c["error"] == 0
        mark = "PASS" if ok else "FAIL"
        line = (
            f"{module:<{name_width}}  {mark}  "
            f"{c['passed']}/{total} passed"
            + (f", {c['failed']} failed" if c["failed"] else "")
            + (f", {c['error']} error" if c["error"] else "")
            + (f", {c['skipped']} skipped" if c["skipped"] else "")
        )
        tr.write_line(line, green=ok, red=not ok)
