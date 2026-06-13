"""Tests for the generated ``hdlpkg(1)`` man page (``scripts/gen_manpage.py``).

The page is introspected from the live CLI parser, so these tests guard two things:
the render covers every subcommand and the expected sections, and the committed
``man/hdlpkg.1`` is up to date with the generator (so a CLI change cannot silently
leave the manual stale).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from hdl_ip_packager import cli

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "gen_manpage.py"
_PAGE = _ROOT / "man" / "hdlpkg.1"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_manpage", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_has_core_sections() -> None:
    page = _load_generator().render_manpage()
    assert page.startswith(".TH HDLPKG 1")
    for section in (
        ".SH NAME",
        ".SH SYNOPSIS",
        ".SH DESCRIPTION",
        ".SH COMMANDS",
        ".SH TYPICAL WORKFLOW",
        ".SH REGISTRIES",
        ".SH FILES",
        ".SH EXAMPLES",
    ):
        assert section in page, f"missing {section}"


def test_render_documents_every_subcommand() -> None:
    page = _load_generator().render_manpage()
    parser = cli.build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    for name in sub.choices:
        assert f".SS {name}" in page, f"man page does not document '{name}'"


def test_render_is_lf_only() -> None:
    # A man page with CR bytes makes groff warn "invalid input character code 13".
    assert "\r" not in _load_generator().render_manpage()


def test_committed_page_is_up_to_date() -> None:
    page = _load_generator().render_manpage()
    committed = _PAGE.open(encoding="utf-8", newline="").read()
    assert committed == page, (
        "man/hdlpkg.1 is stale; regenerate with 'python scripts/gen_manpage.py'."
    )
