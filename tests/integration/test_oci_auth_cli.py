"""Integration test: the OCI token-exchange auth flow, end to end via the CLI.

A live mock that behaves like a managed OCI registry (Harbor/cloud): every ``/v2/``
request without a valid *access token* is answered ``401`` + ``WWW-Authenticate:
Bearer realm=...,service=...,scope=...``. The realm is a separate token endpoint that
checks HTTP Basic credentials (or issues a pull-only token anonymously) and returns a
short-lived access token. This exercises the full challenge -> exchange -> retry path
that ``hdlpkg login --username`` enables, which a no-auth/static-bearer registry does
not require.
"""

from __future__ import annotations

import base64
import json
import shutil
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from hdlpkg import cli

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
_USER = "robot"
_PASSWORD = "s3cret"
_ACCESS_TOKEN = "issued-access-token"


class _Server(ThreadingHTTPServer):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.blobs: dict[str, dict[str, bytes]] = {}
        self.manifests: dict[str, dict[str, bytes]] = {}
        self.host = ""  # filled in once the port is known (for the realm URL)
        self.exchanges = 0  # how many token exchanges happened (asserted by a test)


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, *args: object) -> None:
        return

    def _reply(self, status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    # --- the token endpoint (the "realm") ---------------------------------------
    def _serve_token(self) -> None:
        self.server.exchanges += 1
        auth = self.headers.get("Authorization", "")
        scope = parse_qs(urlsplit(self.path).query).get("scope", [""])[0]
        wants_push = "push" in scope
        if auth.startswith("Basic "):
            decoded = base64.b64decode(auth.split(" ", 1)[1]).decode()
            if decoded != f"{_USER}:{_PASSWORD}":
                return self._reply(401)  # wrong credentials
            return self._reply(200, json.dumps({"token": _ACCESS_TOKEN}).encode())
        # anonymous: issue a pull-only token, never a push token
        if wants_push:
            return self._reply(401)
        return self._reply(200, json.dumps({"token": _ACCESS_TOKEN}).encode())

    def _authed(self) -> bool:
        if self.headers.get("Authorization") == f"Bearer {_ACCESS_TOKEN}":
            return True
        scope = "push,pull" if self.command in ("PUT", "POST") else "pull"
        realm = f"http://{self.server.host}/token"
        self._reply(
            401,
            headers={
                "WWW-Authenticate": (
                    f'Bearer realm="{realm}",service="reg",'
                    f'scope="repository:ip/acme/common/fifo:{scope}"'
                )
            },
        )
        return False

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/token":
            return self._serve_token()
        if not self._authed():
            return
        if path == "/v2/":
            return self._reply(200, b"{}")
        if path.endswith("/tags/list"):
            repo = path[len("/v2/") : -len("/tags/list")]
            return self._reply(
                200, json.dumps({"tags": sorted(self.server.manifests.get(repo, {}))}).encode()
            )
        if "/manifests/" in path:
            repo, _, ref = path[len("/v2/") :].partition("/manifests/")
            blob = self.server.manifests.get(repo, {}).get(ref)
            return self._reply(200, blob) if blob else self._reply(404)
        if "/blobs/" in path:
            repo, _, digest = path[len("/v2/") :].partition("/blobs/")
            blob = self.server.blobs.get(repo, {}).get(digest)
            return self._reply(200, blob) if blob else self._reply(404)
        self._reply(404)

    def do_HEAD(self) -> None:
        if not self._authed():
            return
        repo, _, digest = urlsplit(self.path).path[len("/v2/") :].partition("/blobs/")
        self._reply(200 if digest in self.server.blobs.get(repo, {}) else 404)

    def do_POST(self) -> None:
        if not self._authed():
            return
        repo = self.path[len("/v2/") : -len("/blobs/uploads/")]
        self._reply(202, headers={"Location": f"/v2/{repo}/blobs/uploads/{uuid.uuid4().hex}"})

    def do_PUT(self) -> None:
        if not self._authed():
            return
        split = urlsplit(self.path)
        body = self._body()
        if "/blobs/uploads/" in split.path:
            repo = split.path[len("/v2/") : split.path.index("/blobs/uploads/")]
            digest = split.query.split("digest=", 1)[1]
            self.server.blobs.setdefault(repo, {})[digest] = body
            return self._reply(201)
        repo, _, ref = split.path[len("/v2/") :].partition("/manifests/")
        self.server.manifests.setdefault(repo, {})[ref] = body
        self._reply(201)


@contextmanager
def _serve() -> Iterator[_Server]:
    server = _Server(("127.0.0.1", 0), _Handler)
    server.host = f"127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Hermetic: do not read the developer's real hdlpkg/docker credentials.
    monkeypatch.setenv("HDLPKG_CREDENTIALS", str(tmp_path / "credentials.toml"))
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path / "docker-empty"))


def _location(server: _Server) -> str:
    return f"oci+http://{server.host}/ip"


def test_publish_resolve_with_token_exchange(tmp_path: Path) -> None:
    with _serve() as server:
        loc = _location(server)
        assert cli.main(["login", loc, "--username", _USER, "--token", _PASSWORD]) == 0

        # publish needs a push-scoped token; resolve needs a pull-scoped one -- both via exchange.
        assert cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", loc]) == 0
        manifest = tmp_path / "consumer" / "ip.toml"
        manifest.parent.mkdir()
        shutil.copy(EXAMPLES / "fifo" / "ip.toml", manifest)  # a leaf core: no deps to fetch
        assert cli.main(["resolve", str(manifest), "--registry", loc]) == 0
        assert server.exchanges > 0  # the exchange actually happened


def test_wrong_password_fails(tmp_path: Path) -> None:
    with _serve() as server:
        loc = _location(server)
        assert cli.main(["login", loc, "--username", _USER, "--token", "wrong"]) == 0
        rc = cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", loc])
        assert rc == 1  # exchange rejected -> still 401 -> failure


def test_anonymous_pull_token_allows_resolve_but_not_publish(tmp_path: Path) -> None:
    # No login at all: the registry's token endpoint issues a pull-only token anonymously.
    with _serve() as server:
        loc = _location(server)
        # seed a core by publishing it with valid creds first...
        assert cli.main(["login", loc, "--username", _USER, "--token", _PASSWORD]) == 0
        assert cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", loc]) == 0
        # ...then forget the creds and confirm an anonymous resolve (pull) still works.
        assert cli.main(["logout", loc]) == 0
        manifest = tmp_path / "anon" / "ip.toml"
        manifest.parent.mkdir()
        shutil.copy(EXAMPLES / "fifo" / "ip.toml", manifest)
        assert cli.main(["resolve", str(manifest), "--registry", loc]) == 0
        # but an anonymous publish (push scope) is refused by the token endpoint.
        bumped = tmp_path / "anon" / "v2"
        bumped.mkdir()
        text = (
            (EXAMPLES / "fifo" / "ip.toml")
            .read_text()
            .replace('version = "1.0.0"', 'version = "1.0.1"')
        )
        (bumped / "ip.toml").write_text(text, encoding="utf-8")
        shutil.copytree(EXAMPLES / "fifo" / "rtl", bumped / "rtl")
        shutil.copytree(EXAMPLES / "fifo" / "tb", bumped / "tb")
        assert cli.main(["publish", str(bumped / "ip.toml"), "--registry", loc]) == 1
