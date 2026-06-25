"""Unit tests for CompositeRegistry: union versions, first-wins delegation, warnings."""

from __future__ import annotations

import pytest

from hdlpkg.exceptions import RegistryError
from hdlpkg.manifest import Manifest
from hdlpkg.registry import (
    CompositeRegistry,
    Registry,
    composite_registry_from_locations,
)
from hdlpkg.vlnv import PackageRef, Vlnv

pytestmark = pytest.mark.unit


class FakeRegistry(Registry):
    """An in-memory registry over a fixed ``{vlnv: bytes}`` map, with a stable label."""

    def __init__(self, label: str, cores: dict[Vlnv, bytes], *, broken: bool = False) -> None:
        self.location = label
        self._cores = cores
        self._broken = broken

    def versions(self, ref: PackageRef) -> list[Vlnv]:
        if self._broken:
            raise RegistryError(f"{self.location} is down")
        return [vlnv for vlnv in self._cores if vlnv.ref == ref]

    def manifest(self, vlnv: Vlnv) -> Manifest:
        if vlnv not in self._cores:
            raise RegistryError(f"{vlnv} absent")
        return Manifest(vlnv=vlnv)

    def artifact_bytes(self, vlnv: Vlnv) -> bytes:
        if vlnv not in self._cores:
            raise RegistryError(f"{vlnv} absent")
        return self._cores[vlnv]

    def source_for(self, vlnv: Vlnv) -> str:
        return f"{self.location}#{vlnv}"


def _vlnv(name: str, version: str = "1.0.0") -> Vlnv:
    return Vlnv.parse(f"acme:common:{name}:{version}")


def test_versions_unions_across_registries_deduplicated() -> None:
    shared = _vlnv("fifo", "1.0.0")
    only_b = _vlnv("fifo", "2.0.0")
    reg_a = FakeRegistry("A", {shared: b"a"})
    reg_b = FakeRegistry("B", {shared: b"a", only_b: b"b"})
    composite = CompositeRegistry([reg_a, reg_b])

    versions = composite.versions(PackageRef.parse("acme:common:fifo"))

    assert set(versions) == {shared, only_b}
    assert len(versions) == 2  # the shared version appears once
    assert versions[0] == shared  # first-seen order preserved


def test_manifest_and_source_delegate_to_first_registry_with_the_vlnv() -> None:
    vlnv = _vlnv("fifo")
    reg_a = FakeRegistry("A", {})  # does not have it
    reg_b = FakeRegistry("B", {vlnv: b"b"})
    composite = CompositeRegistry([reg_a, reg_b])

    assert composite.manifest(vlnv).vlnv == vlnv
    assert composite.source_for(vlnv) == f"B#{vlnv}"
    assert composite.artifact_bytes(vlnv) == b"b"
    assert composite.warnings == []  # only one registry has it -> no shadow warning


def test_first_in_order_wins_when_a_vlnv_is_shadowed_and_a_warning_is_recorded() -> None:
    vlnv = _vlnv("fifo")
    first = FakeRegistry("A", {vlnv: b"from-a"})
    second = FakeRegistry("B", {vlnv: b"from-b"})
    composite = CompositeRegistry([first, second])

    assert composite.artifact_bytes(vlnv) == b"from-a"  # first-in-order wins
    assert composite.source_for(vlnv) == f"A#{vlnv}"
    assert len(composite.warnings) == 1
    warning = composite.warnings[0]
    assert "multiple registries" in warning
    assert "using A" in warning and "B" in warning


def test_shadow_warning_is_emitted_only_once_per_vlnv() -> None:
    vlnv = _vlnv("fifo")
    composite = CompositeRegistry(
        [FakeRegistry("A", {vlnv: b"a"}), FakeRegistry("B", {vlnv: b"b"})]
    )

    composite.manifest(vlnv)
    composite.artifact_bytes(vlnv)
    composite.source_for(vlnv)

    assert len(composite.warnings) == 1


def test_unreachable_registry_is_skipped_with_a_warning() -> None:
    vlnv = _vlnv("fifo")
    down = FakeRegistry("down", {}, broken=True)
    up = FakeRegistry("up", {vlnv: b"ok"})
    composite = CompositeRegistry([down, up])

    # versions() unions over what is reachable; the broken backend is skipped.
    assert composite.versions(vlnv.ref) == [vlnv]
    assert composite.artifact_bytes(vlnv) == b"ok"
    assert any("unreachable" in w and "down" in w for w in composite.warnings)


def test_unreachable_warning_is_deduplicated() -> None:
    down = FakeRegistry("down", {}, broken=True)
    up = FakeRegistry("up", {_vlnv("fifo"): b"ok"})
    composite = CompositeRegistry([down, up])

    composite.versions(PackageRef.parse("acme:common:fifo"))
    composite.versions(PackageRef.parse("acme:common:other"))

    assert sum("unreachable" in w for w in composite.warnings) == 1


def test_owner_raises_when_no_registry_has_the_vlnv() -> None:
    composite = CompositeRegistry([FakeRegistry("A", {})])
    with pytest.raises(RegistryError, match="not available in any configured registry"):
        composite.manifest(_vlnv("missing"))


def test_constructing_an_empty_composite_is_an_error() -> None:
    with pytest.raises(RegistryError, match="at least one backend"):
        CompositeRegistry([])


def test_from_locations_single_location_is_not_wrapped(tmp_path) -> None:
    # A single location returns the concrete backend directly (no composite wrapper).
    registry = composite_registry_from_locations([str(tmp_path)])
    assert not isinstance(registry, CompositeRegistry)


def test_from_locations_multiple_locations_build_a_composite(tmp_path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    registry = composite_registry_from_locations([str(tmp_path), str(other)])
    assert isinstance(registry, CompositeRegistry)


def test_from_locations_requires_at_least_one() -> None:
    with pytest.raises(RegistryError):
        composite_registry_from_locations([])
