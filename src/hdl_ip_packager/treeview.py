"""Render a resolved dependency graph as an ASCII tree (behind ``hdlpkg tree``).

Pure presentation: :func:`render_dependency_tree` takes the root manifest, the
resolver's choice of one :class:`~hdl_ip_packager.vlnv.Vlnv` per package, and the
resolved manifests (so it can recurse into each dependency's own dependencies),
and returns the printable string. No I/O -- the CLI supplies the resolved data.
"""

from __future__ import annotations

from collections.abc import Mapping

from .manifest import Dependency, Manifest
from .vlnv import PackageRef, Vlnv

__all__ = ["render_dependency_tree"]


def render_dependency_tree(
    root: Manifest,
    resolved: Mapping[PackageRef, Vlnv],
    manifests: Mapping[PackageRef, Manifest],
) -> str:
    """Return an ASCII dependency tree for *root*.

    Args:
        root: the top-level manifest whose dependencies head the tree.
        resolved: the chosen VLNV for every reachable package (``Resolution.selected``).
        manifests: the resolved manifest for each package, used to recurse into a
            dependency's own ``[dependencies]``.

    A package that appears more than once is expanded only on its first occurrence;
    later occurrences are marked ``(*)`` so the output stays finite and readable.
    """
    lines = [str(root.vlnv)]
    expanded: set[PackageRef] = set()

    def walk(deps: tuple[Dependency, ...], prefix: str) -> None:
        items = sorted(deps, key=lambda d: str(d.ref))
        for index, dep in enumerate(items):
            last = index == len(items) - 1
            connector = "`-- " if last else "|-- "
            vlnv = resolved.get(dep.ref)
            version = str(vlnv.version) if vlnv is not None else "(unresolved)"
            repeated = dep.ref in expanded
            marker = " (*)" if repeated else ""
            lines.append(f"{prefix}{connector}{dep.ref} {dep.constraint} -> {version}{marker}")
            if vlnv is None or repeated:
                continue
            expanded.add(dep.ref)
            child = manifests.get(dep.ref)
            if child is not None and child.dependencies:
                walk(child.dependencies, prefix + ("    " if last else "|   "))

    walk(root.dependencies, "")
    return "\n".join(lines)
