"""Dependency resolution (planned).

The resolver turns a root :class:`~hdl_ip_packager.manifest.Manifest` plus the set of
available core versions into a concrete, reproducible solution: one chosen
:class:`~hdl_ip_packager.vlnv.Vlnv` per package that satisfies every constraint. The
solution is what gets written to the lockfile (``ip.lock``).

Design intent (see ``docs/architecture.md`` and ``docs/research/state_of_the_art.md``):

* Strategy: pick the **newest** version satisfying all constraints (the pip/npm/
  Cargo convention), excluding pre-releases unless explicitly requested.
* Version selection across a dependency graph is NP-complete in the general case,
  so the long-term implementation will lower to a SAT/CDCL solver. The first cut
  can be a simple backtracking search over the (small) candidate sets.
* Output is order-independent and deterministic so the lockfile is stable.

This module currently exposes the intended types and signatures only; the bodies
raise :class:`NotImplementedError`. Implementing it is the next major milestone.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .manifest import Manifest
from .vlnv import PackageRef, Vlnv

__all__ = ["Resolution", "resolve"]


@dataclass(frozen=True)
class Resolution:
    """The result of a successful resolve: one concrete version per package."""

    selected: Mapping[PackageRef, Vlnv]


def resolve(
    root: Manifest,
    available: Mapping[PackageRef, Iterable[Vlnv]],
) -> Resolution:
    """Resolve *root*'s dependency graph against the *available* versions.

    Args:
        root: the top-level manifest whose dependencies drive the solve.
        available: for each package, the versions known to a registry/cache.

    Returns:
        A :class:`Resolution` mapping every required package to one chosen VLNV.

    Raises:
        ResolutionError: if no assignment satisfies all constraints.
    """
    raise NotImplementedError(
        "Dependency resolution is planned. See docs/progress_tracker.md (Roadmap)."
    )
