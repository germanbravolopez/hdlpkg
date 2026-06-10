"""Render a resolved dependency graph as an ASCII tree (behind ``hdlpkg tree``).

Pure presentation: :func:`render_dependency_tree` takes the root manifest, the
resolver's selected :class:`~hdl_ip_packager.vlnv.Vlnv`\\ (s) per package, and the
resolved manifests (so it can recurse into each dependency's own dependencies),
and returns the printable string. No I/O -- the CLI supplies the resolved data.

A package may be selected at more than one (incompatible) version under the
``isolate_namespaces`` conflict policy; each distinct version expands on its own,
so the tree shows the coexistence honestly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .manifest import Dependency, Manifest
from .version import VersionConstraint
from .vlnv import PackageRef, Vlnv

__all__ = ["render_dependency_tree"]


def _pick(selected: Sequence[Vlnv], constraint: VersionConstraint) -> Vlnv | None:
    """The selected VLNV an edge resolves to: the newest satisfying one, else None."""
    matching = [v for v in selected if constraint.matches(v.version)]
    if not matching:
        return None
    return max(matching, key=lambda v: v.version)


def render_dependency_tree(
    root: Manifest,
    resolved: Mapping[PackageRef, Sequence[Vlnv]],
    manifests: Mapping[Vlnv, Manifest],
) -> str:
    """Return an ASCII dependency tree for *root*.

    Args:
        root: the top-level manifest whose dependencies head the tree.
        resolved: the selected VLNV(s) for every reachable package
            (``Resolution.by_ref``).
        manifests: the resolved manifest for each selected VLNV, used to recurse
            into a dependency's own ``[dependencies]``.

    A VLNV that appears more than once is expanded only on its first occurrence;
    later occurrences are marked ``(*)`` so the output stays finite and readable.
    """
    lines = [str(root.vlnv)]
    expanded: set[Vlnv] = set()

    def walk(deps: tuple[Dependency, ...], prefix: str) -> None:
        items = sorted(deps, key=lambda d: str(d.ref))
        for index, dep in enumerate(items):
            last = index == len(items) - 1
            connector = "`-- " if last else "|-- "
            vlnv = _pick(resolved.get(dep.ref, ()), dep.constraint)
            version = str(vlnv.version) if vlnv is not None else "(unresolved)"
            repeated = vlnv is not None and vlnv in expanded
            marker = " (*)" if repeated else ""
            lines.append(f"{prefix}{connector}{dep.ref} {dep.constraint} -> {version}{marker}")
            if vlnv is None or repeated:
                continue
            expanded.add(vlnv)
            child = manifests.get(vlnv)
            if child is not None and child.dependencies:
                walk(child.dependencies, prefix + ("    " if last else "|   "))

    walk(root.dependencies, "")
    return "\n".join(lines)
