"""Integration test: the writable, authenticated HTTP registry, end to end via the CLI.

A small localhost HTTP server backed by a temp directory serves ``GET`` and accepts
``PUT`` (so it is a real read/write registry) and requires a bearer token on every
request. The test logs in (``hdlpkg login``), publishes cores, then resolves /
installs / pulls them straight from the network registry -- the private self-hosted
flow a company team would use.
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from hdl_ip_packager import cli
from hdl_ip_packager.lockfile import Lockfile

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
_TOKEN = "s3cret-token"


class _AuthFileHandler(SimpleHTTPRequestHandler):
    """A GET+PUT file handler under a root dir, requiring ``Authorization: Bearer``."""

    def log_message(self, *args: object) -> None:  # silence test noise
        return

    def _authorized(self) -> bool:
        if self.headers.get("Authorization") == f"Bearer {_TOKEN}":
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Bearer realm="test"')
        self.end_headers()
        return False

    def do_GET(self) -> None:
        if self._authorized():
            super().do_GET()

    def do_PUT(self) -> None:
        if not self._authorized():
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        target = Path(self.translate_path(self.path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        self.send_response(201)
        self.end_headers()


@contextmanager
def _serve(directory: Path) -> Iterator[str]:
    handler = partial(_AuthFileHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture
def logged_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Serve a temp HTTP registry and log into it; yield its base URL."""
    monkeypatch.setenv("HDLPKG_CREDENTIALS", str(tmp_path / "credentials.toml"))
    with _serve(tmp_path / "registry") as base_url:
        assert cli.main(["login", base_url, "--token", _TOKEN]) == 0
        yield base_url


def _publish(base_url: str, core: str) -> None:
    assert cli.main(["publish", str(EXAMPLES / core / "ip.toml"), "--registry", base_url]) == 0


def test_publish_resolve_install_pull_over_http(logged_in: str, tmp_path: Path) -> None:
    base_url = logged_in
    _publish(base_url, "fifo")
    _publish(base_url, "uart")  # depends on acme:common:fifo ^1.0.0

    manifest = tmp_path / "consumer" / "ip.toml"
    manifest.parent.mkdir()
    shutil.copy(EXAMPLES / "uart" / "ip.toml", manifest)

    assert cli.main(["resolve", str(manifest), "--registry", base_url]) == 0
    lock = Lockfile.from_path(manifest.parent / "ip.lock")
    fifo = next(p for p in lock.packages if p.vlnv.name == "fifo")
    assert str(fifo.vlnv) == "acme:common:fifo:1.0.0"
    assert fifo.source.startswith("registry:http://")

    cache = tmp_path / "cache"
    assert (
        cli.main(
            [
                "install",
                str(manifest),
                "--registry",
                base_url,
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
                base_url,
                "--cache-dir",
                str(cache),
                "--output",
                str(extracted),
            ]
        )
        == 0
    )
    assert next(extracted.rglob("sync_fifo.sv"), None) is not None


def test_publish_is_append_only(logged_in: str) -> None:
    _publish(logged_in, "fifo")
    rc = cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", logged_in])
    assert rc == 1  # already published


def test_missing_token_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HDLPKG_CREDENTIALS", str(tmp_path / "credentials.toml"))
    with _serve(tmp_path / "registry") as base_url:
        # No login: publish must fail closed against the auth-protected server.
        rc = cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", base_url])
        assert rc == 1
