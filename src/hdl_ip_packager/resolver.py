"""Dependency resolution.

The resolver turns a root :class:`~hdl_ip_packager.manifest.Manifest` plus the set
of available core versions into a concrete, reproducible solution: the chosen
:class:`~hdl_ip_packager.vlnv.Vlnv`\\ (s) for every package that satisfy every
constraint. The solution is what gets written to the lockfile (``ip.lock``).

Design (see ``docs/architecture.md`` and ``docs/research/state_of_the_art.md``):

* **Compatibility unification (Cargo-style).** Dependents whose ranges fall in the
  same *compatibility group* -- same major for SemVer (see
  :func:`~hdl_ip_packager.version.compatibility_group`) -- always unify to the
  single newest version satisfying them all. A diamond on ``^1.0`` + ``^1.1``
  resolves to one ``1.1.x``.
* **Conflict policy.** Only a genuinely *incompatible* conflict -- two SemVer
  majors, or two distinct exact pins of an ``opaque``-scheme package -- is governed
  by a :data:`~hdl_ip_packager.manifest.ConflictPolicy`:

  - ``fail_on_conflict`` (default): raise :class:`ResolutionError`.
  - ``use_latest``: collapse to the newest of the conflicting versions and warn.
  - ``isolate_namespaces``: keep every incompatible version (multi-version
    bookkeeping). HDL cannot host two namespaces in one elaboration without
    name-mangling, which is unbuilt, so ``gen`` refuses to emit two versions -- the
    resolver still records them so the lock/tree are honest.
* **Backtracking search** over candidate sets, keyed per *(package, compatibility
  group)* node, so two incompatible majors are two independent nodes that each
  resolve to one version. Choosing the newest version can make a transitive
  constraint unsatisfiable, so the search falls back to older versions.
* **Pure**: the available versions are passed in (the registry/cache layer fetches
  them), so the solve does no I/O and is deterministic.

``available`` maps each package to the *manifests* of its known versions -- not
just the version numbers -- because a candidate's own ``[dependencies]`` and its
declared version *scheme* drive the transitive solve.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .exceptions import ResolutionError
from .manifest import DEFAULT_CONFLICT_POLICY, ConflictPolicy, Manifest
from .version import VersionConstraint, VersionScheme, compatibility_group
from .vlnv import PackageRef, Vlnv

__all__ = ["Resolution", "resolve"]

# A search node: a package plus one of its compatibility groups. Two incompatible
# groups of the same package are two nodes, each resolving to a single version.
_Group = tuple[object, ...]
_Node = tuple[PackageRef, _Group]


@dataclass(frozen=True)
class Resolution:
    """The result of a successful resolve: the chosen versions for every package.

    Usually one version per package; with ``isolate_namespaces`` a package may
    appear at more than one (incompatible) version. ``warnings`` records any
    policy-driven compromises (a ``use_latest`` override, an isolated coexistence).
    """

    packages: tuple[Vlnv, ...]
    warnings: tuple[str, ...] = field(default=())

    @property
    def vlnvs(self) -> tuple[Vlnv, ...]:
        """The selected VLNVs in a deterministic (sorted) order."""
        return tuple(sorted(self.packages, key=str))

    @property
    def by_ref(self) -> dict[PackageRef, tuple[Vlnv, ...]]:
        """The selected VLNVs grouped by package reference (sorted within each)."""
        out: dict[PackageRef, list[Vlnv]] = {}
        for vlnv in self.vlnvs:
            out.setdefault(vlnv.ref, []).append(vlnv)
        return {ref: tuple(vlnvs) for ref, vlnvs in out.items()}


def resolve(
    root: Manifest,
    available: Mapping[PackageRef, Sequence[Manifest]],
    policy: ConflictPolicy | None = None,
) -> Resolution:
    """Resolve *root*'s dependency graph against the *available* versions.

    Args:
        root: the top-level manifest whose dependencies drive the solve.
        available: for each package, the manifests of the versions a registry/cache
            offers. Each candidate's own dependencies are followed transitively.
        policy: how to handle an incompatible conflict; defaults to the root
            manifest's ``[resolution] on-conflict`` (``fail_on_conflict`` if unset).

    Returns:
        A :class:`Resolution` listing every required package's chosen VLNV(s).

    Raises:
        ResolutionError: if no assignment satisfies all constraints, or an
            incompatible conflict is hit under ``fail_on_conflict``.
    """
    effective = policy or root.conflict_policy or DEFAULT_CONFLICT_POLICY
    index: dict[PackageRef, list[Manifest]] = {
        ref: sorted(manifests, key=lambda m: m.vlnv.version, reverse=True)
        for ref, manifests in available.items()
    }
    schemes: dict[PackageRef, VersionScheme] = {
        ref: manifests[0].version_scheme for ref, manifests in index.items() if manifests
    }

    initial: dict[_Node, list[VersionConstraint]] = {}
    for dep in root.dependencies:
        node = _edge_node(dep.ref, dep.constraint, index, schemes)
        initial.setdefault(node, []).append(dep.constraint)

    failures: list[str] = []
    assignment = _solve(initial, {}, index, schemes, failures)
    if assignment is None:
        detail = failures[-1] if failures else "the constraints cannot be satisfied"
        raise ResolutionError(f"Could not resolve dependencies: {detail}.")

    chosen, warnings = _apply_policy(assignment, effective)
    reachable = _collect_reachable(root, chosen)
    packages = tuple(sorted((m.vlnv for m in reachable), key=str))
    return Resolution(packages=packages, warnings=tuple(warnings))


def _scheme_of(ref: PackageRef, schemes: Mapping[PackageRef, VersionScheme]) -> VersionScheme:
    return schemes.get(ref, "semver")


def _edge_node(
    ref: PackageRef,
    constraint: VersionConstraint,
    index: Mapping[PackageRef, list[Manifest]],
    schemes: Mapping[PackageRef, VersionScheme],
) -> _Node:
    """The ``(ref, group)`` node a single dependency edge belongs to.

    For an opaque package the constraint must be an exact pin (raises otherwise) and
    each distinct pin is its own group. For an *ordered* scheme (semver/calver/
    monotonic) the group is that of the newest available version satisfying the
    constraint (so a caret range maps to one compatibility group); if none satisfy,
    the newest available version's group keeps the node so the search reports a clear
    "no version satisfies" failure.
    """
    scheme = _scheme_of(ref, schemes)
    candidates = index.get(ref, [])
    if scheme == "opaque":
        token = constraint.pinned_token
        if token is None:
            raise ResolutionError(
                f"{ref} uses the 'opaque' version scheme; dependents must pin an exact "
                f"'=' version, got {constraint}."
            )
        return (ref, ("opaque", token))
    if not candidates:
        return (ref, ("missing",))
    satisfying = [m for m in candidates if constraint.matches(m.vlnv.version)]
    pivot = satisfying[0] if satisfying else candidates[0]  # index is newest-first
    return (ref, compatibility_group(pivot.vlnv.version, scheme))


def _solve(
    constraints: dict[_Node, list[VersionConstraint]],
    assignment: dict[_Node, Manifest],
    index: dict[PackageRef, list[Manifest]],
    schemes: dict[PackageRef, VersionScheme],
    failures: list[str],
) -> dict[_Node, Manifest] | None:
    """Backtracking core. Return a complete node assignment, or None on failure."""
    pending = sorted(
        (node for node in constraints if node not in assignment),
        key=lambda n: (str(n[0]), repr(n[1])),
    )
    if not pending:
        return dict(assignment)

    node = pending[0]
    ref, group = node
    clauses = constraints[node]
    candidates = index.get(ref)
    if not candidates:
        failures.append(f"no versions of {ref} are available")
        return None

    viable = [
        m
        for m in candidates
        if compatibility_group(m.vlnv.version, _scheme_of(ref, schemes)) == group
        and all(c.matches(m.vlnv.version) for c in clauses)
    ]
    if not viable:
        wanted = ", ".join(str(c) for c in clauses)
        have = ", ".join(str(m.vlnv.version) for m in candidates)
        failures.append(f"no version of {ref} satisfies {wanted} (available: {have})")
        return None

    for manifest in viable:  # candidates are pre-sorted newest-first
        next_assignment = {**assignment, node: manifest}
        next_constraints, conflict = _extend(constraints, manifest, next_assignment, index, schemes)
        if conflict is not None:
            failures.append(conflict)
            continue
        result = _solve(next_constraints, next_assignment, index, schemes, failures)
        if result is not None:
            return result
    return None


def _extend(
    constraints: dict[_Node, list[VersionConstraint]],
    manifest: Manifest,
    assignment: dict[_Node, Manifest],
    index: dict[PackageRef, list[Manifest]],
    schemes: dict[PackageRef, VersionScheme],
) -> tuple[dict[_Node, list[VersionConstraint]], str | None]:
    """Add *manifest*'s dependencies as constraints on their nodes; report a conflict
    with an already-chosen version in the same group if one is introduced."""
    extended = {node: list(clauses) for node, clauses in constraints.items()}
    for dep in manifest.dependencies:
        node = _edge_node(dep.ref, dep.constraint, index, schemes)
        extended.setdefault(node, []).append(dep.constraint)
        chosen = assignment.get(node)
        if chosen is not None and not dep.constraint.matches(chosen.vlnv.version):
            conflict = (
                f"{manifest.vlnv} requires {dep.ref} {dep.constraint}, "
                f"but {chosen.vlnv.version} is already selected"
            )
            return extended, conflict
    return extended, None


def _apply_policy(
    assignment: Mapping[_Node, Manifest],
    policy: ConflictPolicy,
) -> tuple[dict[PackageRef, list[Manifest]], list[str]]:
    """Fold the per-node assignment into per-package selections under *policy*.

    A package with more than one node is an incompatible conflict. ``fail_on_conflict``
    raises; ``use_latest`` keeps the newest and warns; ``isolate_namespaces`` keeps all.
    """
    by_ref: dict[PackageRef, list[Manifest]] = {}
    for (ref, _group), manifest in assignment.items():
        by_ref.setdefault(ref, []).append(manifest)

    chosen: dict[PackageRef, list[Manifest]] = {}
    warnings: list[str] = []
    for ref, manifests in by_ref.items():
        if len(manifests) == 1:
            chosen[ref] = manifests
            continue
        versions = ", ".join(
            str(m.vlnv.version) for m in sorted(manifests, key=lambda m: m.vlnv.version)
        )
        if policy == "fail_on_conflict":
            raise ResolutionError(
                f"Could not resolve dependencies: {ref} is required at incompatible versions "
                f"({versions}); no single version satisfies all dependents. Set [resolution] "
                f"on-conflict to 'use_latest' or 'isolate_namespaces' to allow this."
            )
        if policy == "use_latest":
            newest = max(manifests, key=lambda m: m.vlnv.version)
            chosen[ref] = [newest]
            warnings.append(
                f"{ref}: incompatible versions {versions} collapsed to {newest.vlnv.version} "
                f"(use_latest); lower requirements may be violated."
            )
        else:  # isolate_namespaces
            chosen[ref] = sorted(manifests, key=lambda m: m.vlnv.version)
            warnings.append(
                f"{ref}: keeping incompatible versions {versions} side by side "
                f"(isolate_namespaces); 'gen' name-mangles coexisting SystemVerilog/VHDL packages "
                f"(module/entity coexistence is still refused)."
            )
    return chosen, warnings


def _collect_reachable(
    root: Manifest,
    chosen: Mapping[PackageRef, list[Manifest]],
) -> list[Manifest]:
    """Walk the graph from *root*, picking each edge's selected manifest.

    This prunes anything orphaned by a ``use_latest`` collapse and, for
    ``isolate_namespaces``, follows each edge to the version in its own group.
    """
    result: dict[Vlnv, Manifest] = {}
    queue = [dep for dep in root.dependencies]
    while queue:
        dep = queue.pop()
        candidates = chosen.get(dep.ref)
        if not candidates:
            continue
        pick = _pick_for_edge(candidates, dep.constraint)
        if pick.vlnv in result:
            continue
        result[pick.vlnv] = pick
        queue.extend(pick.dependencies)
    return list(result.values())


def _pick_for_edge(candidates: Sequence[Manifest], constraint: VersionConstraint) -> Manifest:
    """The selected manifest an edge resolves to: the newest satisfying one, or --
    when a ``use_latest`` collapse means none satisfies -- the newest available."""
    matching = [m for m in candidates if constraint.matches(m.vlnv.version)]
    pool = matching or list(candidates)
    return max(pool, key=lambda m: m.vlnv.version)
