"""Tests for the registry backends (local directory + HTTP) and the graph walker.

``LocalDirectoryRegistry`` and the HTTP server below both touch the filesystem /
network, so these are integration tests. They cover discovery, fetch-into-cache,
the dependency-graph walk that feeds the resolver, and the failure modes.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from hdl_ip_packager import registry as registry_mod
from hdl_ip_packager.cache import ContentAddressedCache
from hdl_ip_packager.exceptions import RegistryError
from hdl_ip_packager.lockfile import sha256_digest
from hdl_ip_packager.manifest import Manifest
from hdl_ip_packager.registry import (
    HttpRegistry,
    LocalDirectoryRegistry,
    Registry,
    available_from_registry,
)
from hdl_ip_packager.vlnv import PackageRef, Vlnv

pytestmark = pytest.mark.integration

_REPO = Path(__file__).resolve().parents[2]
_EXAMPLES = _REPO / "examples"


def _write_core(root: Path, vlnv: str, deps: dict[str, str] | None = None) -> Path:
    vendor, library, name, version = vlnv.split(":")
    body = [
        "[package]",
        f'vendor = "{vendor}"',
        f'library = "{library}"',
        f'name = "{name}"',
        f'version = "{version}"',
    ]
    if deps:
        body.append("[dependencies]")
        body += [f'"{ref}" = "{spec}"' for ref, spec in deps.items()]
    path = root / vendor / library / name / version
    path.mkdir(parents=True, exist_ok=True)
    manifest = path / "ip.toml"
    manifest.write_text("\n".join(body) + "\n", encoding="utf-8")
    return manifest


def test_registry_abc_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        Registry()  # type: ignore[abstract]


# ----------------------------------------------------------- local directory
def test_local_registry_discovers_and_serves_examples() -> None:
    registry = LocalDirectoryRegistry([_EXAMPLES])
    fifo = PackageRef.parse("acme:common:fifo")
    versions = registry.versions(fifo)
    assert [str(v) for v in versions] == ["acme:common:fifo:1.0.0"]
    manifest = registry.manifest(versions[0])
    assert isinstance(manifest, Manifest)
    assert registry.source_for(versions[0]) == "path:examples/fifo"


def test_local_registry_fetch_stores_verified_blob(tmp_path: Path) -> None:
    registry = LocalDirectoryRegistry([_EXAMPLES])
    vlnv = Vlnv.parse("acme:common:fifo:1.0.0")
    cache = ContentAddressedCache(tmp_path)
    digest = registry.fetch(vlnv, cache)
    assert digest == sha256_digest(registry.artifact_bytes(vlnv))
    assert cache.get(digest) == registry.artifact_bytes(vlnv)


def test_local_registry_unknown_vlnv_raises() -> None:
    registry = LocalDirectoryRegistry([_EXAMPLES])
    with pytest.raises(RegistryError, match="not in the local registry"):
        registry.manifest(Vlnv.parse("acme:common:fifo:9.9.9"))


def test_local_registry_unknown_package_has_no_versions(tmp_path: Path) -> None:
    registry = LocalDirectoryRegistry([tmp_path])
    assert registry.versions(PackageRef.parse("no:such:core")) == []


def test_available_from_registry_walks_the_graph(tmp_path: Path) -> None:
    _write_core(tmp_path, "acme:lib:top:1.0.0")  # not referenced; ignored
    _write_core(tmp_path, "acme:lib:a:1.0.0", {"acme:lib:b": "^1.0.0"})
    _write_core(tmp_path, "acme:lib:b:1.0.0")
    _write_core(tmp_path, "acme:lib:b:1.1.0")
    registry = LocalDirectoryRegistry([tmp_path])
    root = Manifest.from_str(
        '[package]\nvendor="acme"\nlibrary="lib"\nname="root"\nversion="1.0.0"\n'
        '[dependencies]\n"acme:lib:a" = "^1.0.0"\n'
    )
    index = available_from_registry(registry, root)
    assert set(index) == {PackageRef.parse("acme:lib:a"), PackageRef.parse("acme:lib:b")}
    assert {str(m.vlnv) for m in index[PackageRef.parse("acme:lib:b")]} == {
        "acme:lib:b:1.0.0",
        "acme:lib:b:1.1.0",
    }


# --------------------------------------------------------------------- HTTP
@contextmanager
def _serve(directory: Path) -> Iterator[str]:
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()


def _write_http_layout(root: Path) -> None:
    core = root / "acme" / "common" / "fifo"
    (core / "1.0.0").mkdir(parents=True)
    (core / "versions.json").write_text(json.dumps(["1.0.0"]), encoding="utf-8")
    (core / "1.0.0" / "ip.toml").write_text(
        '[package]\nvendor="acme"\nlibrary="common"\nname="fifo"\nversion="1.0.0"\n',
        encoding="utf-8",
    )


def test_http_registry_versions_manifest_and_fetch(tmp_path: Path) -> None:
    _write_http_layout(tmp_path)
    with _serve(tmp_path) as base_url:
        registry = HttpRegistry(base_url)
        ref = PackageRef.parse("acme:common:fifo")
        versions = registry.versions(ref)
        assert [str(v) for v in versions] == ["acme:common:fifo:1.0.0"]
        assert registry.manifest(versions[0]).vlnv == versions[0]
        cache = ContentAddressedCache(tmp_path / "cache")
        digest = registry.fetch(versions[0], cache)
        assert cache.get(digest) == registry.artifact_bytes(versions[0])


def test_http_registry_unknown_package_has_no_versions(tmp_path: Path) -> None:
    with _serve(tmp_path) as base_url:
        registry = HttpRegistry(base_url)
        assert registry.versions(PackageRef.parse("no:such:core")) == []


def test_http_registry_missing_manifest_raises(tmp_path: Path) -> None:
    with _serve(tmp_path) as base_url:
        registry = HttpRegistry(base_url)
        with pytest.raises(RegistryError, match="request failed"):
            registry.artifact_bytes(Vlnv.parse("acme:common:fifo:1.0.0"))


def test_module_exports_registry_symbols() -> None:
    assert registry_mod.Registry is Registry
