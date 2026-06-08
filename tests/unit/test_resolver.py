"""Unit tests for the dependency resolver.

The resolver is pure, so these tests build small in-memory dependency graphs (a
root manifest plus the manifests a registry would offer) and assert the chosen
versions. Coverage spans the happy paths (newest-compatible, transitive, diamond),
the failure modes (conflict, missing package, pre-release exclusion), and the
backtracking that makes newest-first selection complete.
"""

from __future__ import annotations

import pytest

from hdl_ip_packager.exceptions import ResolutionError
from hdl_ip_packager.manifest import Dependency, Manifest
from hdl_ip_packager.resolver import Resolution, resolve
from hdl_ip_packager.version import OpaqueVersion, VersionConstraint
from hdl_ip_packager.vlnv import PackageRef, Vlnv

pytestmark = pytest.mark.unit


def core(vlnv: str, deps: dict[str, str] | None = None) -> Manifest:
    """Build a manifest for *vlnv* with ``{ref: constraint}`` dependencies."""
    dependencies = tuple(
        Dependency(PackageRef.parse(ref), VersionConstraint.parse(spec))
        for ref, spec in (deps or {}).items()
    )
    return Manifest(vlnv=Vlnv.parse(vlnv), dependencies=dependencies)


def available(*manifests: Manifest) -> dict[PackageRef, list[Manifest]]:
    """Group candidate manifests by package, as a registry would expose them."""
    index: dict[PackageRef, list[Manifest]] = {}
    for manifest in manifests:
        index.setdefault(manifest.ref, []).append(manifest)
    return index


def chosen(resolution: Resolution, ref: str) -> str:
    """The single selected version string for *ref* (asserts exactly one)."""
    selected = resolution.by_ref[PackageRef.parse(ref)]
    assert len(selected) == 1, f"expected one version of {ref}, got {selected}"
    return str(selected[0])


def core_scheme(vlnv: str, scheme: str, deps: dict[str, str] | None = None) -> Manifest:
    """Like :func:`core` but with an explicit version *scheme* (e.g. ``opaque``)."""
    return Manifest(
        vlnv=Vlnv.parse(vlnv),
        version_scheme=scheme,  # type: ignore[arg-type]
        dependencies=core(vlnv, deps).dependencies,
    )


def test_no_dependencies_resolves_to_empty() -> None:
    resolution = resolve(core("acme:lib:top:1.0.0"), {})
    assert resolution.by_ref == {}
    assert resolution.vlnvs == ()


def test_picks_newest_compatible() -> None:
    root = core("acme:lib:top:1.0.0", {"acme:lib:a": "^1.0.0"})
    index = available(
        core("acme:lib:a:1.0.0"),
        core("acme:lib:a:1.1.0"),
        core("acme:lib:a:2.0.0"),  # excluded by caret upper bound
    )
    resolution = resolve(root, index)
    assert chosen(resolution, "acme:lib:a") == "acme:lib:a:1.1.0"


def test_transitive_dependency_is_followed() -> None:
    root = core("acme:lib:top:1.0.0", {"acme:lib:a": "^1.0.0"})
    index = available(
        core("acme:lib:a:1.0.0", {"acme:lib:b": "^2.0.0"}),
        core("acme:lib:b:2.3.0"),
        core("acme:lib:b:2.4.0"),
    )
    resolution = resolve(root, index)
    assert chosen(resolution, "acme:lib:a") == "acme:lib:a:1.0.0"
    assert chosen(resolution, "acme:lib:b") == "acme:lib:b:2.4.0"


def test_diamond_intersects_constraints() -> None:
    root = core("acme:lib:top:1.0.0", {"acme:lib:a": "^1.0.0", "acme:lib:b": "^1.0.0"})
    index = available(
        core("acme:lib:a:1.0.0", {"acme:lib:c": "^1.0.0"}),
        core("acme:lib:b:1.0.0", {"acme:lib:c": "^1.2.0"}),
        core("acme:lib:c:1.0.0"),
        core("acme:lib:c:1.2.0"),
        core("acme:lib:c:1.3.0"),  # satisfies >=1.2.0 and <2.0.0 -> newest pick
        core("acme:lib:c:2.0.0"),
    )
    resolution = resolve(root, index)
    assert chosen(resolution, "acme:lib:c") == "acme:lib:c:1.3.0"


def test_conflicting_constraints_raise() -> None:
    root = core("acme:lib:top:1.0.0", {"acme:lib:a": "^1.0.0", "acme:lib:b": "^1.0.0"})
    index = available(
        core("acme:lib:a:1.0.0", {"acme:lib:c": "^1.0.0"}),
        core("acme:lib:b:1.0.0", {"acme:lib:c": "^2.0.0"}),
        core("acme:lib:c:1.5.0"),
        core("acme:lib:c:2.0.0"),
    )
    with pytest.raises(ResolutionError, match="acme:lib:c"):
        resolve(root, index)


def test_missing_package_raises() -> None:
    root = core("acme:lib:top:1.0.0", {"acme:lib:a": "^1.0.0"})
    with pytest.raises(ResolutionError, match="no versions of acme:lib:a"):
        resolve(root, {})


def test_prerelease_excluded_by_default() -> None:
    root = core("acme:lib:top:1.0.0", {"acme:lib:a": "^1.0.0"})
    index = available(core("acme:lib:a:1.0.0-rc.1"))
    with pytest.raises(ResolutionError, match="no version of acme:lib:a"):
        resolve(root, index)


def test_prerelease_allowed_when_targeted() -> None:
    root = core("acme:lib:top:1.0.0", {"acme:lib:a": ">=1.0.0-rc.1,<2.0.0"})
    index = available(core("acme:lib:a:1.0.0-rc.1"))
    resolution = resolve(root, index)
    assert chosen(resolution, "acme:lib:a") == "acme:lib:a:1.0.0-rc.1"


def test_backtracks_to_older_version_when_newest_is_unsatisfiable() -> None:
    # a:1.1.0 needs b ^2 (unavailable); the resolver must fall back to a:1.0.0.
    root = core("acme:lib:top:1.0.0", {"acme:lib:a": "^1.0.0"})
    index = available(
        core("acme:lib:a:1.0.0", {"acme:lib:b": "^1.0.0"}),
        core("acme:lib:a:1.1.0", {"acme:lib:b": "^2.0.0"}),
        core("acme:lib:b:1.0.0"),
    )
    resolution = resolve(root, index)
    assert chosen(resolution, "acme:lib:a") == "acme:lib:a:1.0.0"
    assert chosen(resolution, "acme:lib:b") == "acme:lib:b:1.0.0"


def test_vlnvs_property_is_sorted() -> None:
    root = core("acme:lib:top:1.0.0", {"acme:lib:b": "^1.0.0", "acme:lib:a": "^1.0.0"})
    index = available(core("acme:lib:a:1.0.0"), core("acme:lib:b:1.0.0"))
    resolution = resolve(root, index)
    assert [str(v) for v in resolution.vlnvs] == ["acme:lib:a:1.0.0", "acme:lib:b:1.0.0"]


# --- conflict policies (multi-version coexistence) --------------------------


def _conflict_index() -> dict[PackageRef, list[Manifest]]:
    """The demo's soc_conflict: fifo wants bus ^1, legacy wants bus ^2."""
    return available(
        core("acme:ip:fifo:1.0.0", {"acme:common:bus": "^1.0.0"}),
        core("acme:ip:legacy:1.0.0", {"acme:common:bus": "^2.0.0"}),
        core("acme:common:bus:1.0.0"),
        core("acme:common:bus:1.1.0"),
        core("acme:common:bus:2.0.0"),
    )


def _conflict_root() -> Manifest:
    return core("acme:soc:top:1.0.0", {"acme:ip:fifo": "^1.0.0", "acme:ip:legacy": "^1.0.0"})


def test_incompatible_majors_fail_by_default() -> None:
    with pytest.raises(ResolutionError, match="incompatible versions"):
        resolve(_conflict_root(), _conflict_index())


def test_isolate_namespaces_keeps_both_majors() -> None:
    resolution = resolve(_conflict_root(), _conflict_index(), "isolate_namespaces")
    bus = [str(v) for v in resolution.by_ref[PackageRef.parse("acme:common:bus")]]
    assert bus == ["acme:common:bus:1.1.0", "acme:common:bus:2.0.0"]
    assert any("isolate_namespaces" in w for w in resolution.warnings)


def test_use_latest_collapses_to_newest_and_warns() -> None:
    resolution = resolve(_conflict_root(), _conflict_index(), "use_latest")
    assert chosen(resolution, "acme:common:bus") == "acme:common:bus:2.0.0"
    assert any("use_latest" in w and "2.0.0" in w for w in resolution.warnings)


def test_compatible_diamond_unifies_regardless_of_policy() -> None:
    # fifo ^1.0 + arbiter ^1.1 are SemVer-compatible -> one shared bus, no warning.
    root = core("acme:soc:top:1.0.0", {"acme:ip:fifo": "^1.0.0", "acme:ip:arbiter": "^1.0.0"})
    index = available(
        core("acme:ip:fifo:1.0.0", {"acme:common:bus": "^1.0.0"}),
        core("acme:ip:arbiter:1.0.0", {"acme:common:bus": "^1.1.0"}),
        core("acme:common:bus:1.0.0"),
        core("acme:common:bus:1.1.0"),
        core("acme:common:bus:2.0.0"),
    )
    resolution = resolve(root, index, "isolate_namespaces")
    assert chosen(resolution, "acme:common:bus") == "acme:common:bus:1.1.0"
    assert resolution.warnings == ()


def test_policy_defaults_to_manifest_setting() -> None:
    root = Manifest(
        vlnv=Vlnv.parse("acme:soc:top:1.0.0"),
        conflict_policy="isolate_namespaces",
        dependencies=_conflict_root().dependencies,
    )
    resolution = resolve(root, _conflict_index())  # no explicit policy arg
    assert len(resolution.by_ref[PackageRef.parse("acme:common:bus")]) == 2


# --- opaque version scheme (honor-exact-pins) -------------------------------


def test_opaque_distinct_pins_are_incompatible() -> None:
    root = core("acme:soc:top:1.0.0", {"acme:x:vendor_ip": "=1.0.0", "acme:ip:wrap": "^1.0.0"})
    index = available(
        core("acme:ip:wrap:1.0.0", {"acme:x:vendor_ip": "=2.0.0"}),
        core_scheme("acme:x:vendor_ip:1.0.0", "opaque"),
        core_scheme("acme:x:vendor_ip:2.0.0", "opaque"),
    )
    # Two distinct exact pins of an opaque core do not unify -> conflict.
    with pytest.raises(ResolutionError, match="incompatible versions"):
        resolve(root, index)
    resolution = resolve(root, index, "isolate_namespaces")
    assert len(resolution.by_ref[PackageRef.parse("acme:x:vendor_ip")]) == 2


def test_opaque_same_pin_unifies() -> None:
    root = core("acme:soc:top:1.0.0", {"acme:x:vendor_ip": "=1.0.0", "acme:ip:wrap": "^1.0.0"})
    index = available(
        core("acme:ip:wrap:1.0.0", {"acme:x:vendor_ip": "=1.0.0"}),
        core_scheme("acme:x:vendor_ip:1.0.0", "opaque"),
        core_scheme("acme:x:vendor_ip:2.0.0", "opaque"),
    )
    resolution = resolve(root, index)
    assert chosen(resolution, "acme:x:vendor_ip") == "acme:x:vendor_ip:1.0.0"


def test_opaque_requires_exact_constraint() -> None:
    root = core("acme:soc:top:1.0.0", {"acme:x:vendor_ip": "^1.0.0"})
    index = available(core_scheme("acme:x:vendor_ip:1.0.0", "opaque"))
    with pytest.raises(ResolutionError, match="exact '=' version"):
        resolve(root, index)


def _opaque_core(ref: str, token: str) -> Manifest:
    """An opaque-scheme core whose version is a genuinely non-SemVer vendor token."""
    return Manifest(
        vlnv=PackageRef.parse(ref).with_version(OpaqueVersion.parse(token)),
        version_scheme="opaque",
    )


def test_non_semver_opaque_tokens_resolve_by_exact_pin() -> None:
    # Vendor tags like D5020100 / D4010100 / DB010000 -- exact-pinned, never ranged.
    root = core(
        "acme:soc:top:1.0.0",
        {"acme:rf:radio": "=D5020100", "acme:dsp:filter": "=D4010100", "acme:bus:db": "=DB010000"},
    )
    index = available(
        _opaque_core("acme:rf:radio", "D5020100"),
        _opaque_core("acme:rf:radio", "D5020200"),  # a different tag, not selected
        _opaque_core("acme:dsp:filter", "D4010100"),
        _opaque_core("acme:bus:db", "DB010000"),
    )
    resolution = resolve(root, index)
    assert chosen(resolution, "acme:rf:radio") == "acme:rf:radio:D5020100"
    assert chosen(resolution, "acme:dsp:filter") == "acme:dsp:filter:D4010100"
    assert chosen(resolution, "acme:bus:db") == "acme:bus:db:DB010000"


def test_distinct_opaque_tags_conflict_under_default_policy() -> None:
    root = core("acme:soc:top:1.0.0", {"acme:rf:radio": "=D5020100", "acme:ip:wrap": "^1.0.0"})
    index = available(
        core("acme:ip:wrap:1.0.0", {"acme:rf:radio": "=D5020200"}),
        _opaque_core("acme:rf:radio", "D5020100"),
        _opaque_core("acme:rf:radio", "D5020200"),
    )
    with pytest.raises(ResolutionError, match="incompatible versions"):
        resolve(root, index)
    resolution = resolve(root, index, "isolate_namespaces")
    assert len(resolution.by_ref[PackageRef.parse("acme:rf:radio")]) == 2
