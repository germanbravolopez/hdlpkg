"""Unit test: the Makefile integration example stays consistent with the CLI surface.

Guards the cheap-to-break invariant that ``examples/integration/hdlpkg.mk`` keeps using real
``hdlpkg`` commands/flags, so renaming the ``gen --format filelist`` surface fails here
instead of silently breaking the customer-facing example.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
HDLPKG_MK = REPO_ROOT / "examples" / "integration" / "hdlpkg.mk"
QUESTA_MK = REPO_ROOT / "examples" / "integration" / "questa" / "Makefile"


def test_example_makefiles_exist() -> None:
    assert HDLPKG_MK.is_file()
    assert QUESTA_MK.is_file()


def test_hdlpkg_mk_uses_real_cli_surface() -> None:
    text = HDLPKG_MK.read_text(encoding="utf-8")
    assert "$(HDLPKG) install" in text
    assert "--format filelist" in text  # the emitter the example depends on
    for target in ("hdlpkg-install:", "hdlpkg-filelist:", "hdlpkg-clean:"):
        assert target in text


def test_questa_example_includes_the_shared_mk_and_reads_filelists() -> None:
    text = QUESTA_MK.read_text(encoding="utf-8")
    assert "include ../hdlpkg.mk" in text
    assert "hdlpkg-filelist" in text  # compile depends on the IP filelists
    assert "$(HDLPKG_OUT)" in text  # and reads them from the output dir
