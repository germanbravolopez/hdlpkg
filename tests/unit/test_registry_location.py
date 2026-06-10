"""Unit tests for registry_from_location: scheme dispatch + credential wiring."""

from __future__ import annotations

import pytest

from hdl_ip_packager.credentials import CredentialStore
from hdl_ip_packager.exceptions import RegistryError
from hdl_ip_packager.registry import (
    HttpRegistry,
    LocalRegistry,
    OciRegistry,
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
