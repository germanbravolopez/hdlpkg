"""Unit tests for registry_from_lock_source + LockSourceRegistry (Phase 2: locked fetch)."""

from __future__ import annotations

import pytest

from hdlpkg.exceptions import RegistryError
from hdlpkg.registry import (
    HttpRegistry,
    LocalDirectoryRegistry,
    LocalRegistry,
    LockSourceRegistry,
    OciRegistry,
    Registry,
    registry_from_lock_source,
)
from hdlpkg.vlnv import PackageRef, Vlnv

pytestmark = pytest.mark.unit


def _vlnv(name: str = "fifo", version: str = "1.0.0") -> Vlnv:
    return Vlnv.parse(f"acme:common:{name}:{version}")


def test_path_source_builds_a_local_directory_registry(tmp_path) -> None:
    registry = registry_from_lock_source(f"path:{tmp_path}")
    assert isinstance(registry, LocalDirectoryRegistry)


def test_registry_source_with_a_path_builds_a_local_store(tmp_path) -> None:
    registry = registry_from_lock_source(f"registry:{tmp_path}")
    assert isinstance(registry, LocalRegistry)


def test_registry_source_with_an_http_url_builds_an_http_registry() -> None:
    registry = registry_from_lock_source("registry:https://ip.corp.local/acme")
    assert isinstance(registry, HttpRegistry)
    assert registry.base_url == "https://ip.corp.local/acme"


def test_oci_source_reconstructs_the_base_dropping_the_vlnv_tail() -> None:
    # oci:<host>/<prefix>/<vendor>/<library>/<name>:<version> -> oci://<host>/<prefix>
    registry = registry_from_lock_source("oci:harbor.corp/ip/acme/common/fifo:1.0.0")
    assert isinstance(registry, OciRegistry)
    assert registry.host == "harbor.corp"
    assert registry.prefix == "ip"
    assert registry.transport == "https"  # the recorded source has no scheme


def test_oci_source_without_a_prefix_reconstructs_the_bare_host() -> None:
    registry = registry_from_lock_source("oci:harbor.corp/acme/common/fifo:1.0.0")
    assert isinstance(registry, OciRegistry)
    assert registry.host == "harbor.corp"
    assert registry.prefix == ""


def test_git_source_delegates_to_registry_from_location(monkeypatch) -> None:
    # A git+ source is passed through verbatim (constructing a real GitRegistry would clone).
    seen: list[str] = []

    def fake_from_location(location: str, *, credentials=None) -> Registry:
        seen.append(location)
        return _FakeBackend(_vlnv(), b"")

    monkeypatch.setattr("hdlpkg.registry.registry_from_location", fake_from_location)
    source = "git+ssh://example.com/org/ip.git@" + "0" * 40
    registry_from_lock_source(source)
    assert seen == [source]


@pytest.mark.parametrize(
    "source",
    ["", "oci:harbor.corp/fifo:1.0.0", "oci:harbor.corp/acme/common/fifo"],
)
def test_unparseable_sources_raise(source: str) -> None:
    with pytest.raises(RegistryError):
        registry_from_lock_source(source)


class _FakeBackend(Registry):
    def __init__(self, vlnv: Vlnv, payload: bytes) -> None:
        self._vlnv = vlnv
        self._payload = payload

    def versions(self, ref: PackageRef) -> list[Vlnv]:
        return [self._vlnv] if self._vlnv.ref == ref else []

    def manifest(self, vlnv: Vlnv):  # pragma: no cover - not exercised here
        raise RegistryError("unused")

    def artifact_bytes(self, vlnv: Vlnv) -> bytes:
        return self._payload


def test_lock_source_registry_dispatches_per_package(monkeypatch) -> None:
    a, b = _vlnv("fifo"), _vlnv("uart")
    built: list[str] = []

    def fake_from_source(source: str, *, credentials=None) -> Registry:
        built.append(source)
        return _FakeBackend(a if "a-store" in source else b, source.encode())

    monkeypatch.setattr("hdlpkg.registry.registry_from_lock_source", fake_from_source)
    registry = LockSourceRegistry({a: "registry:a-store", b: "registry:b-store"})

    assert registry.artifact_bytes(a) == b"registry:a-store"
    assert registry.artifact_bytes(b) == b"registry:b-store"
    assert registry.source_for(a) == "registry:a-store"
    assert set(built) == {"registry:a-store", "registry:b-store"}


def test_lock_source_registry_caches_backends_per_source(monkeypatch) -> None:
    a, b = _vlnv("fifo"), _vlnv("fifo", "2.0.0")
    calls: list[str] = []

    def fake_from_source(source: str, *, credentials=None) -> Registry:
        calls.append(source)
        return _FakeBackend(_vlnv("x"), b"")

    monkeypatch.setattr("hdlpkg.registry.registry_from_lock_source", fake_from_source)
    registry = LockSourceRegistry({a: "registry:same", b: "registry:same"})
    registry.artifact_bytes(a)
    registry.artifact_bytes(b)

    assert calls == ["registry:same"]  # one shared source -> built once


def test_lock_source_registry_versions_returns_pinned_vlnvs_only() -> None:
    a = _vlnv("fifo")
    registry = LockSourceRegistry({a: "registry:store"})
    assert registry.versions(a.ref) == [a]
    assert registry.versions(PackageRef.parse("acme:common:other")) == []


def test_lock_source_registry_unpinned_and_sourceless_raise() -> None:
    a = _vlnv("fifo")
    registry = LockSourceRegistry({a: ""})
    with pytest.raises(RegistryError, match="no recorded source"):
        registry.artifact_bytes(a)
    with pytest.raises(RegistryError, match="not pinned"):
        registry.artifact_bytes(_vlnv("missing"))
