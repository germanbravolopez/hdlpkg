"""Unit tests for the stored-credentials subsystem (pure store + host keying + I/O)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hdl_ip_packager.credentials import (
    CredentialStore,
    default_credentials_path,
    load_credentials,
    registry_host,
    save_credentials,
)
from hdl_ip_packager.exceptions import CredentialsError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("https://ip.corp.local/acme", "ip.corp.local"),
        ("http://Reg.Corp:8080/x", "reg.corp:8080"),
        ("oci://harbor.corp/ip/acme", "harbor.corp"),
        ("oci+http://127.0.0.1:5000/ip", "127.0.0.1:5000"),
        ("/var/lib/registry", None),
        ("path:./reg", None),
        ("C:\\\\registry", None),
    ],
)
def test_registry_host(location: str, expected: str | None) -> None:
    assert registry_host(location) == expected


def test_registry_host_rejects_network_url_without_host() -> None:
    with pytest.raises(CredentialsError, match="no host"):
        registry_host("https:///nohost")


def test_store_token_lookup_is_case_insensitive_on_host() -> None:
    store = CredentialStore().with_token("Harbor.Corp", "tok")
    assert store.token_for("harbor.corp") == "tok"
    assert store.token_for("HARBOR.CORP") == "tok"
    assert store.token_for("other.host") is None
    assert store.token_for(None) is None


def test_store_with_and_without_token_are_immutable() -> None:
    base = CredentialStore()
    one = base.with_token("h1", "a")
    two = one.with_token("h2", "b")
    assert base.tokens == {}  # original untouched
    assert one.tokens == {"h1": "a"}
    assert two.without("h1").tokens == {"h2": "b"}
    assert two.without("absent").tokens == two.tokens  # idempotent


def test_store_toml_round_trip_escapes_special_characters() -> None:
    store = CredentialStore().with_token("h", 'tok"with\\back')
    assert CredentialStore.from_toml(store.to_toml()).tokens == store.tokens


def test_from_toml_rejects_malformed_documents() -> None:
    with pytest.raises(CredentialsError, match="Malformed"):
        CredentialStore.from_toml("not = [valid")
    with pytest.raises(CredentialsError, match="must be a table"):
        CredentialStore.from_toml("tokens = 1\n")
    with pytest.raises(CredentialsError, match="must be a string"):
        CredentialStore.from_toml("[tokens]\nh = 1\n")


def test_load_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_credentials(tmp_path / "absent.toml").tokens == {}


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "credentials.toml"
    save_credentials(CredentialStore().with_token("harbor.corp", "tok"), path)
    assert path.is_file()
    assert load_credentials(path).token_for("harbor.corp") == "tok"


def test_default_path_honors_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "creds.toml"
    monkeypatch.setenv("HDLPKG_CREDENTIALS", str(target))
    assert default_credentials_path() == target
