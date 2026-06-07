"""Unit tests for the dependency-tree renderer (pure, no I/O)."""

from __future__ import annotations

import pytest

from hdl_ip_packager.manifest import Manifest
from hdl_ip_packager.treeview import render_dependency_tree

pytestmark = pytest.mark.unit

LEAF = """\
[package]
vendor = "acme"
library = "x"
name = "leaf"
version = "1.0.0"
"""

MID = """\
[package]
vendor = "acme"
library = "x"
name = "mid"
version = "1.0.0"
[dependencies]
"acme:x:leaf" = "^1.0.0"
"""

TOP = """\
[package]
vendor = "acme"
library = "app"
name = "top"
version = "2.0.0"
[dependencies]
"acme:x:leaf" = "^1.0.0"
"acme:x:mid" = "^1.0.0"
"""


def _build() -> tuple[Manifest, dict, dict]:
    leaf, mid, top = (Manifest.from_str(t) for t in (LEAF, MID, TOP))
    resolved = {leaf.ref: leaf.vlnv, mid.ref: mid.vlnv}
    manifests = {leaf.ref: leaf, mid.ref: mid}
    return top, resolved, manifests


def test_tree_has_root_line_and_sorted_children() -> None:
    top, resolved, manifests = _build()
    out = render_dependency_tree(top, resolved, manifests).splitlines()
    assert out[0] == "acme:app:top:2.0.0"
    assert out[1].startswith("|-- acme:x:leaf")  # sorted before mid
    assert out[2].startswith("`-- acme:x:mid")


def test_tree_annotates_resolved_versions() -> None:
    top, resolved, manifests = _build()
    out = render_dependency_tree(top, resolved, manifests)
    assert "acme:x:mid ^1.0.0 -> 1.0.0" in out


def test_repeated_node_is_marked_and_not_re_expanded() -> None:
    top, resolved, manifests = _build()
    out = render_dependency_tree(top, resolved, manifests)
    # leaf appears twice: once at top level, once under mid (the second marked *).
    assert out.count("(*)") == 1
    mid_branch = out.splitlines()[-1]
    assert "acme:x:leaf" in mid_branch and mid_branch.strip().endswith("(*)")


def test_output_is_ascii_safe() -> None:
    # Box-drawing characters crash on a cp1252 Windows console; keep it ASCII.
    top, resolved, manifests = _build()
    assert render_dependency_tree(top, resolved, manifests).isascii()


def test_unresolved_dependency_is_labelled() -> None:
    top = Manifest.from_str(TOP)
    out = render_dependency_tree(top, {}, {})
    assert out.count("(unresolved)") == 2
