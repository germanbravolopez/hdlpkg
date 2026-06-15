"""Integration test: the OCI distribution backend, end to end via the CLI.

A minimal in-memory OCI distribution v2 server (the subset hdlpkg uses: blob upload,
manifest/tag put + get, tags list, bearer auth) stands in for a real registry such as
Harbor / Zot / Artifactory, so the publish -> resolve -> install -> pull flow is
exercised honestly in CI without a live external service. The client speaks plain HTTP
via the ``oci+http://`` transport.
"""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hdlpkg import cli
from hdlpkg.lockfile import Lockfile

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
_TOKEN = "oci-token"


class _OciServer(ThreadingHTTPServer):
    """Holds the registry's in-memory state shared across handler invocations."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.blobs: dict[str, dict[str, bytes]] = {}  # repo -> digest -> bytes
        self.manifests: dict[str, dict[str, bytes]] = {}  # repo -> reference -> bytes


class _OciHandler(BaseHTTPRequestHandler):
    """The minimal OCI distribution v2 endpoints hdlpkg's OciRegistry calls."""

    server: _OciServer

    def log_message(self, *args: object) -> None:
        return

    def _authorized(self) -> bool:
        if self.headers.get("Authorization") == f"Bearer {_TOKEN}":
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Bearer realm="test"')
        self.end_headers()
        return False

    def _reply(self, status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self) -> None:
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        if path == "/v2/":
            return self._reply(200, b"{}")
        if path.endswith("/tags/list"):
            repo = path[len("/v2/") : -len("/tags/list")]
            tags = sorted(self.server.manifests.get(repo, {}))
            return self._reply(200, json.dumps({"name": repo, "tags": tags}).encode())
        if "/manifests/" in path:
            repo, _, reference = path[len("/v2/") :].partition("/manifests/")
            blob = self.server.manifests.get(repo, {}).get(reference)
            return self._reply(200, blob) if blob else self._reply(404)
        if "/blobs/" in path:
            repo, _, digest = path[len("/v2/") :].partition("/blobs/")
            blob = self.server.blobs.get(repo, {}).get(digest)
            return self._reply(200, blob) if blob else self._reply(404)
        self._reply(404)

    def do_HEAD(self) -> None:
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        repo, _, digest = path[len("/v2/") :].partition("/blobs/")
        present = digest in self.server.blobs.get(repo, {})
        self._reply(200 if present else 404)

    def do_POST(self) -> None:
        if not self._authorized():
            return
        # Start a blob upload: hand back an opaque upload URL the client PUTs to.
        repo = self.path[len("/v2/") : -len("/blobs/uploads/")]
        location = f"/v2/{repo}/blobs/uploads/{uuid.uuid4().hex}"
        self._reply(202, headers={"Location": location})

    def do_PUT(self) -> None:
        if not self._authorized():
            return
        split = urlsplit(self.path)
        path, query = split.path, split.query
        body = self._body()
        if "/blobs/uploads/" in path:
            repo = path[len("/v2/") : path.index("/blobs/uploads/")]
            digest = query.split("digest=", 1)[1]
            self.server.blobs.setdefault(repo, {})[digest] = body
            return self._reply(201, headers={"Docker-Content-Digest": digest})
        if "/manifests/" in path:
            repo, _, reference = path[len("/v2/") :].partition("/manifests/")
            self.server.manifests.setdefault(repo, {})[reference] = body
            return self._reply(201)
        self._reply(400)


@contextmanager
def _serve() -> Iterator[str]:
    server = _OciServer(("127.0.0.1", 0), _OciHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        yield f"oci+http://{host}:{port}/ip"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture
def logged_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("HDLPKG_CREDENTIALS", str(tmp_path / "credentials.toml"))
    with _serve() as location:
        assert cli.main(["login", location, "--token", _TOKEN]) == 0
        yield location


def _publish(location: str, core: str) -> None:
    assert cli.main(["publish", str(EXAMPLES / core / "ip.toml"), "--registry", location]) == 0


def test_publish_resolve_install_pull_over_oci(logged_in: str, tmp_path: Path) -> None:
    location = logged_in
    _publish(location, "fifo")
    _publish(location, "uart")

    manifest = tmp_path / "consumer" / "ip.toml"
    manifest.parent.mkdir()
    shutil.copy(EXAMPLES / "uart" / "ip.toml", manifest)

    assert cli.main(["resolve", str(manifest), "--registry", location]) == 0
    lock = Lockfile.from_path(manifest.parent / "ip.lock")
    fifo = next(p for p in lock.packages if p.vlnv.name == "fifo")
    assert str(fifo.vlnv) == "acme:common:fifo:1.0.0"
    assert fifo.source.startswith("oci:")

    cache = tmp_path / "cache"
    assert (
        cli.main(
            [
                "install",
                str(manifest),
                "--registry",
                location,
                "--cache-dir",
                str(cache),
                "--locked",
            ]
        )
        == 0
    )
    assert any(cache.rglob("*"))

    extracted = tmp_path / "pulled"
    assert (
        cli.main(
            [
                "pull",
                "acme:common:fifo:1.0.0",
                "--registry",
                location,
                "--cache-dir",
                str(cache),
                "--output",
                str(extracted),
            ]
        )
        == 0
    )
    assert next(extracted.rglob("sync_fifo.sv"), None) is not None
    assert next(extracted.rglob("ip.toml"), None) is not None


def test_oci_publish_is_append_only(logged_in: str) -> None:
    _publish(logged_in, "fifo")
    rc = cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", logged_in])
    assert rc == 1


def test_oci_unknown_package_has_no_versions(logged_in: str, tmp_path: Path) -> None:
    # A manifest depending on an unpublished core resolves to nothing for that ref.
    manifest = tmp_path / "ip.toml"
    shutil.copy(EXAMPLES / "uart" / "ip.toml", manifest)  # needs fifo, which is not published
    rc = cli.main(["resolve", str(manifest), "--registry", logged_in])
    assert rc == 1  # unsatisfied dependency -> resolution error


def test_oci_requires_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HDLPKG_CREDENTIALS", str(tmp_path / "credentials.toml"))
    with _serve() as location:
        rc = cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", location])
        assert rc == 1  # not logged in -> 401 -> failure


def test_oci_backend_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    from hdlpkg.credentials import Credential
    from hdlpkg.exceptions import RegistryError
    from hdlpkg.registry import OciRegistry
    from hdlpkg.vlnv import Vlnv

    with _serve() as location:
        registry = OciRegistry(location, credential=Credential(_TOKEN))
        absent = Vlnv.parse("acme:common:fifo:1.0.0")
        with pytest.raises(RegistryError, match="not in OCI registry"):
            registry.manifest(absent)
        with pytest.raises(RegistryError, match="not in OCI registry"):
            registry.artifact_bytes(absent)
        with pytest.raises(RegistryError, match="does not support yanking"):
            registry.yank(absent)


def test_oci_location_without_host_is_rejected() -> None:
    from hdlpkg.exceptions import RegistryError
    from hdlpkg.registry import OciRegistry

    with pytest.raises(RegistryError, match="no host"):
        OciRegistry("oci:///no-host")
