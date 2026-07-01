"""Unit tests for lock_satisfies_manifest -- the registry-free install freshness check."""

from __future__ import annotations

import pytest

from hdlpkg.lockfile import LockedPackage, Lockfile, lock_satisfies_manifest
from hdlpkg.manifest import Dependency, Manifest
from hdlpkg.version import VersionConstraint
from hdlpkg.vlnv import PackageRef, Vlnv

pytestmark = pytest.mark.unit


def _manifest(*deps: tuple[str, str]) -> Manifest:
    return Manifest(
        vlnv=Vlnv.parse("me:soc:top:1.0.0"),
        dependencies=tuple(
            Dependency(PackageRef.parse(ref), VersionConstraint.parse(con)) for ref, con in deps
        ),
    )


def _lock(*vlnvs: str) -> Lockfile:
    return Lockfile(packages=tuple(LockedPackage(Vlnv.parse(v)) for v in vlnvs))


def test_no_dependencies_is_trivially_satisfied() -> None:
    assert lock_satisfies_manifest(_manifest(), _lock()) is True


def test_locked_version_within_the_constraint_is_satisfied() -> None:
    manifest = _manifest(("acme:common:fifo", "^1.0.0"))
    assert lock_satisfies_manifest(manifest, _lock("acme:common:fifo:1.2.0")) is True


def test_dependency_absent_from_the_lock_is_not_satisfied() -> None:
    # A dep added to ip.toml but not yet resolved -> stale lock.
    manifest = _manifest(("acme:common:fifo", "^1.0.0"), ("acme:common:uart", "^2.0.0"))
    assert lock_satisfies_manifest(manifest, _lock("acme:common:fifo:1.2.0")) is False


def test_locked_version_outside_a_tightened_constraint_is_not_satisfied() -> None:
    # The constraint was bumped past the locked version -> stale lock.
    manifest = _manifest(("acme:common:fifo", "^2.0.0"))
    assert lock_satisfies_manifest(manifest, _lock("acme:common:fifo:1.2.0")) is False


def test_an_extra_locked_package_does_not_make_it_stale() -> None:
    # A removed dep leaves an unused package in the lock; the direct asks are still met.
    manifest = _manifest(("acme:common:fifo", "^1.0.0"))
    lock = _lock("acme:common:fifo:1.2.0", "acme:common:uart:2.0.0")
    assert lock_satisfies_manifest(manifest, lock) is True


def test_opaque_scheme_exact_pin_is_matched() -> None:
    manifest = Manifest(
        vlnv=Vlnv.parse("me:soc:top:1.0.0"),
        dependencies=(
            Dependency(PackageRef.parse("acme:x:radio"), VersionConstraint.parse("=D5020100")),
        ),
    )
    lock = Lockfile(packages=(LockedPackage(Vlnv.parse("acme:x:radio:D5020100", "opaque")),))
    assert lock_satisfies_manifest(manifest, lock) is True

    stale = Lockfile(packages=(LockedPackage(Vlnv.parse("acme:x:radio:D5020099", "opaque")),))
    assert lock_satisfies_manifest(manifest, stale) is False
