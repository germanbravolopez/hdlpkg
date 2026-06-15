"""Every outbound registry request must carry a non-default ``User-Agent``.

``urllib``'s default ``Python-urllib/3.x`` is rejected by common WAFs (a JFrog
Artifactory behind Cloudflare returned 403 in the trial), so the HTTP and OCI backends
set an explicit ``User-Agent``. These tests fake the transport and assert the header is
present and non-default on all four request paths: ``HttpRegistry`` GET/PUT and
``OciRegistry`` ``_send`` + the token-exchange request.
"""

from __future__ import annotations

import json

import pytest

from hdlpkg import registry as reg
from hdlpkg.registry import _USER_AGENT, HttpRegistry, OciRegistry

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.status = 200
        self.headers: dict[str, str] = {}

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Capture every ``Request`` sent, returning a token-bearing JSON body."""
    seen: list[object] = []

    def fake_urlopen(request: object, *args: object, **kwargs: object) -> _FakeResponse:
        seen.append(request)
        return _FakeResponse(json.dumps({"token": "tok"}).encode())

    monkeypatch.setattr(reg.urllib.request, "urlopen", fake_urlopen)
    return seen


def _user_agents(requests: list[object]) -> list[str | None]:
    return [r.get_header("User-agent") for r in requests]  # type: ignore[attr-defined]


def test_user_agent_constant_is_non_default() -> None:
    assert _USER_AGENT.startswith("hdlpkg")
    assert "Python-urllib" not in _USER_AGENT


def test_http_get_and_put_send_user_agent(captured: list[object]) -> None:
    http = HttpRegistry("http://reg.example/ip", token="t")
    http._get("http://reg.example/ip/x")
    http._put("http://reg.example/ip/x", b"data", "application/octet-stream")
    agents = _user_agents(captured)
    assert len(agents) == 2
    assert all(a == _USER_AGENT for a in agents)


def test_oci_send_carries_user_agent(captured: list[object]) -> None:
    oci = OciRegistry("oci+http://reg.example/ip")
    oci._send("GET", "http://reg.example/v2/ip/manifests/1.0.0", accept="application/json")
    assert _user_agents(captured) == [_USER_AGENT]


def test_oci_token_exchange_carries_user_agent(captured: list[object]) -> None:
    oci = OciRegistry("oci+http://reg.example/ip")
    assert oci._exchange_token({"realm": "http://reg.example/token"}) is True
    assert _user_agents(captured) == [_USER_AGENT]
