"""Unit tests for the text-preserving ip.toml editor (``add_dependency``)."""

from __future__ import annotations

import pytest

from hdl_ip_packager.editing import add_dependency
from hdl_ip_packager.manifest import Manifest
from hdl_ip_packager.version import VersionConstraint
from hdl_ip_packager.vlnv import PackageRef

pytestmark = pytest.mark.unit

BASE = '[package]\nvendor = "acme"\nlibrary = "comm"\nname = "uart"\nversion = "1.0.0"\n'


def _add(text: str, ref: str, constraint: str) -> str:
    return add_dependency(text, PackageRef.parse(ref), VersionConstraint.parse(constraint))


def _deps(text: str) -> dict[str, str]:
    return {str(d.ref): str(d.constraint) for d in Manifest.from_str(text).dependencies}


def test_appends_dependencies_table_when_absent() -> None:
    out = _add(BASE, "acme:common:fifo", "^1.0.0")
    assert "[dependencies]" in out
    assert _deps(out) == {"acme:common:fifo": "^1.0.0"}
    assert out.endswith("\n")


def test_inserts_into_existing_table_preserving_comments() -> None:
    text = BASE + '\n[dependencies]\n# existing\n"acme:common:fifo" = "^1.0.0"\n'
    out = _add(text, "vendorx:axi:bfm", ">=2.0.0,<3.0.0")
    assert "# existing" in out  # comment preserved
    assert _deps(out) == {"acme:common:fifo": "^1.0.0", "vendorx:axi:bfm": ">=2.0.0,<3.0.0"}


def test_updates_existing_dependency_constraint() -> None:
    text = BASE + '\n[dependencies]\n"acme:common:fifo" = "^1.0.0"\n'
    out = _add(text, "acme:common:fifo", "^2.0.0")
    assert _deps(out) == {"acme:common:fifo": "^2.0.0"}
    assert out.count("acme:common:fifo") == 1  # replaced, not duplicated


def test_insert_keeps_following_tables_intact() -> None:
    text = (
        BASE
        + '\n[dependencies]\n"a:b:c" = "^1.0.0"\n'
        + '\n[filesets.rtl]\nfiles = ["rtl/uart.sv"]\ntype = "systemVerilogSource"\n'
    )
    out = _add(text, "x:y:z", "^1.0.0")
    assert "[filesets.rtl]" in out
    parsed = Manifest.from_str(out)
    assert "rtl" in parsed.filesets
    assert _deps(out) == {"a:b:c": "^1.0.0", "x:y:z": "^1.0.0"}
