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
    resolved = {leaf.ref: (leaf.vlnv,), mid.ref: (mid.vlnv,)}
    manifests = {leaf.vlnv: leaf, mid.vlnv: mid}
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


def test_multi_version_edges_pick_their_own_version() -> None:
    # Two majors of one package coexist (isolate_namespaces): each edge resolves
    # to the version satisfying its own constraint.
    bus1 = Manifest.from_str(LEAF)
    bus2 = Manifest.from_str(LEAF.replace('version = "1.0.0"', 'version = "2.0.0"'))
    fifo = Manifest.from_str(MID.replace('name = "mid"', 'name = "fifo"'))
    legacy = Manifest.from_str(
        MID.replace('name = "mid"', 'name = "legacy"').replace(
            '"acme:x:leaf" = "^1.0.0"', '"acme:x:leaf" = "^2.0.0"'
        )
    )
    top = Manifest.from_str(
        TOP.replace('"acme:x:leaf" = "^1.0.0"\n"acme:x:mid" = "^1.0.0"', "").replace(
            "[dependencies]", '[dependencies]\n"acme:x:fifo" = "^1.0.0"\n"acme:x:legacy" = "^1.0.0"'
        )
    )
    resolved = {
        fifo.ref: (fifo.vlnv,),
        legacy.ref: (legacy.vlnv,),
        bus1.ref: (bus1.vlnv, bus2.vlnv),
    }
    manifests = {fifo.vlnv: fifo, legacy.vlnv: legacy, bus1.vlnv: bus1, bus2.vlnv: bus2}
    out = render_dependency_tree(top, resolved, manifests)
    assert "acme:x:leaf ^1.0.0 -> 1.0.0" in out
    assert "acme:x:leaf ^2.0.0 -> 2.0.0" in out
