"""Unit tests for registry_from_location: scheme dispatch + credential wiring."""

from __future__ import annotations

import pytest

from hdlpkg.credentials import CredentialStore
from hdlpkg.exceptions import RegistryError
from hdlpkg.registry import (
    HttpRegistry,
    LocalRegistry,
    OciRegistry,
    _is_full_sha,
    _is_scp_like,
    _parse_git_location,
    parse_bearer_challenge,
    registry_from_location,
)

pytestmark = pytest.mark.unit


def test_parse_bearer_challenge_extracts_params() -> None:
    header = (
        'Bearer realm="https://auth.corp/token",service="registry.corp",'
        'scope="repository:ip/acme:pull,push"'
    )
    assert parse_bearer_challenge(header) == {
        "realm": "https://auth.corp/token",
        "service": "registry.corp",
        "scope": "repository:ip/acme:pull,push",
    }


def test_parse_bearer_challenge_is_case_insensitive_scheme() -> None:
    assert parse_bearer_challenge('bearer realm="https://a/t"') == {"realm": "https://a/t"}


@pytest.mark.parametrize("header", ["", 'Basic realm="x"', 'Bearer service="reg"'])
def test_parse_bearer_challenge_returns_none(header: str) -> None:
    # empty, non-Bearer, or a Bearer challenge with no realm -> not an exchange signal
    assert parse_bearer_challenge(header) is None


def test_bare_path_and_path_scheme_build_local_registry() -> None:
    assert isinstance(registry_from_location("some/dir"), LocalRegistry)
    assert isinstance(registry_from_location("path:some/dir"), LocalRegistry)
    assert isinstance(registry_from_location("file:///srv/reg"), LocalRegistry)
    # A Windows drive letter must not be mistaken for a scheme.
    assert isinstance(registry_from_location("C:\\registry"), LocalRegistry)


def test_http_and_oci_schemes_build_network_backends() -> None:
    assert isinstance(registry_from_location("http://reg.corp/x"), HttpRegistry)
    assert isinstance(registry_from_location("https://reg.corp/x"), HttpRegistry)
    assert isinstance(registry_from_location("oci://harbor.corp/ip"), OciRegistry)
    oci_http = registry_from_location("oci+http://127.0.0.1:5000/ip")
    assert isinstance(oci_http, OciRegistry)
    assert oci_http.transport == "http"


def test_oci_transport_defaults_to_https_and_parses_prefix() -> None:
    reg = registry_from_location("oci://harbor.corp/ip/acme")
    assert isinstance(reg, OciRegistry)
    assert reg.transport == "https"
    assert reg.host == "harbor.corp"
    assert reg.prefix == "ip/acme"


def test_credentials_are_wired_into_network_backends() -> None:
    store = CredentialStore().with_token("harbor.corp", "tok123")
    oci = registry_from_location("oci://harbor.corp/ip", credentials=store)
    http = registry_from_location("https://reg.corp/x", credentials=store)
    assert isinstance(oci, OciRegistry) and oci.credential is not None
    assert oci.credential.secret == "tok123"
    assert isinstance(http, HttpRegistry) and http.token is None  # different host -> no token


def test_unknown_scheme_raises() -> None:
    with pytest.raises(RegistryError, match="Unsupported registry location scheme"):
        registry_from_location("ftp://reg.corp/x")


@pytest.mark.parametrize(
    ("location", "url", "ref"),
    [
        ("git+https://host/org/repo.git", "https://host/org/repo.git", None),
        ("git+https://host/org/repo.git@v1.2.0", "https://host/org/repo.git", "v1.2.0"),
        # An ssh user (git@host) before the path must not be read as a ref.
        ("git+ssh://git@host/org/repo.git", "ssh://git@host/org/repo.git", None),
        ("git+ssh://git@host/org/repo.git@main", "ssh://git@host/org/repo.git", "main"),
        ("git+file:///tmp/reg.git", "file:///tmp/reg.git", None),
        # A ref may contain '/' (git-flow branches) -- it is kept whole, and an ssh
        # userinfo '@' in the same URL is still not mistaken for the ref separator.
        (
            "git+ssh://git@host/org/repo.git@feature/foo",
            "ssh://git@host/org/repo.git",
            "feature/foo",
        ),
        ("git+https://host/org/repo.git@release/1.0", "https://host/org/repo.git", "release/1.0"),
        ("git+file:///tmp/reg.git@develop", "file:///tmp/reg.git", "develop"),
    ],
)
def test_parse_git_location_splits_url_and_ref(location: str, url: str, ref: str | None) -> None:
    assert _parse_git_location(location) == (url, ref)


@pytest.mark.parametrize(
    "location",
    [
        "git@host:org/repo.git",  # bare scp (no git+) -- would fall through to LocalRegistry
        "git+git@host:repo.git",  # scp with a git+ prefix
        "git+git@host:repo.git@v1.0",  # scp + @ref -- the first '@' is ambiguous
    ],
)
def test_scp_style_git_url_is_rejected(location: str) -> None:
    assert _is_scp_like(location)
    with pytest.raises(RegistryError, match="scp-style git URL"):
        registry_from_location(location)


@pytest.mark.parametrize(
    "location",
    [
        "git+ssh://git@host/org/repo.git",  # the supported explicit form
        "git+https://host/org/repo.git",
        "path:some/dir",
        "C:\\registry",
        "some/dir",
    ],
)
def test_non_scp_locations_are_not_flagged(location: str) -> None:
    assert not _is_scp_like(location)


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("0" * 40, True),  # SHA-1
        ("a1b2c3d4" * 5, True),  # 40 hex
        ("f" * 64, True),  # SHA-256
        ("v1.0.0", False),  # a tag
        ("main", False),  # a branch
        ("0" * 39, False),  # too short
        ("g" * 40, False),  # not hex
    ],
)
def test_is_full_sha(ref: str, expected: bool) -> None:
    assert _is_full_sha(ref) is expected
