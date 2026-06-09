"""Stored credentials for authenticating to private registries.

Network registries (HTTP, OCI) backing a company's *private* IP sharing require a
token to read or publish. ``hdlpkg login <registry>`` stores a per-host token in a
user credentials file; ``resolve`` / ``install`` / ``publish`` read it back
automatically and present it as a bearer token, so a team can publish to and consume
from an internal registry without the cores ever being public.

A token is scoped to a **registry host**, not a full URL: ``oci://harbor.corp/ip/acme``
and ``oci://harbor.corp/ip/dsp`` share the one token for ``harbor.corp``. Local
(directory) registries need no credentials, so their location has no host.

Design: the pure :class:`CredentialStore` value type does all parsing/serialization
and host keying, so the logic is unit-testable without touching the filesystem; the
thin :func:`load_credentials` / :func:`save_credentials` pair is the only I/O. The
store is TOML at ``~/.hdlpkg/credentials.toml`` (override with the ``HDLPKG_CREDENTIALS``
environment variable -- used by tests and CI).

Example::

    store = load_credentials().with_token("harbor.corp", "tok_...")
    save_credentials(store)
    token = load_credentials().token_for(registry_host("oci://harbor.corp/ip/acme"))
"""

from __future__ import annotations

import contextlib
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .cache import DEFAULT_CACHE_DIRNAME
from .exceptions import CredentialsError

__all__ = [
    "CREDENTIALS_ENV_VAR",
    "CredentialStore",
    "default_credentials_path",
    "load_credentials",
    "registry_host",
    "save_credentials",
]

CREDENTIALS_ENV_VAR = "HDLPKG_CREDENTIALS"
_CREDENTIALS_FILENAME = "credentials.toml"
_TOKENS_TABLE = "tokens"
_NETWORK_SCHEMES = ("http", "https", "oci", "oci+http")


def registry_host(location: str) -> str | None:
    """The lowercased host a token applies to, or ``None`` for a local-path registry.

    Network locations (``http(s)://`` / ``oci://``) key on their ``host[:port]``;
    a bare path or ``path:``/``file:`` location is local and needs no credentials.
    """
    scheme, _, _ = location.partition("://")
    if scheme.lower() not in _NETWORK_SCHEMES:
        return None
    host = urlsplit(location).netloc.lower()
    if not host:
        raise CredentialsError(f"Registry location has no host: {location!r}")
    return host


@dataclass(frozen=True)
class CredentialStore:
    """An immutable map of registry host -> bearer token."""

    tokens: dict[str, str] = field(default_factory=dict)

    def token_for(self, host: str | None) -> str | None:
        """The stored token for *host* (lowercased), or ``None`` if there is none."""
        if host is None:
            return None
        return self.tokens.get(host.lower())

    def with_token(self, host: str, token: str) -> CredentialStore:
        """A copy of this store with *token* set for *host* (replacing any existing)."""
        updated = dict(self.tokens)
        updated[host.lower()] = token
        return CredentialStore(updated)

    def without(self, host: str) -> CredentialStore:
        """A copy of this store with *host* removed (idempotent)."""
        updated = dict(self.tokens)
        updated.pop(host.lower(), None)
        return CredentialStore(updated)

    def to_toml(self) -> str:
        """Serialize to a deterministic TOML document (hosts sorted)."""
        lines = [f"[{_TOKENS_TABLE}]"]
        for host in sorted(self.tokens):
            token = self.tokens[host].replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'"{host}" = "{token}"')
        return "\n".join(lines) + "\n"

    @classmethod
    def from_toml(cls, text: str) -> CredentialStore:
        """Parse a credentials TOML document; raise :class:`CredentialsError` if malformed."""
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise CredentialsError(f"Malformed credentials file: {exc}") from exc
        raw = data.get(_TOKENS_TABLE, {})
        if not isinstance(raw, dict):
            raise CredentialsError(f"[{_TOKENS_TABLE}] must be a table of host = token.")
        tokens: dict[str, str] = {}
        for host, token in raw.items():
            if not isinstance(token, str):
                raise CredentialsError(f"Token for {host!r} must be a string.")
            tokens[host.lower()] = token
        return cls(tokens)


def default_credentials_path() -> Path:
    """The credentials file path: ``$HDLPKG_CREDENTIALS`` or ``~/.hdlpkg/credentials.toml``."""
    override = os.environ.get(CREDENTIALS_ENV_VAR)
    if override:
        return Path(override)
    return Path.home() / DEFAULT_CACHE_DIRNAME / _CREDENTIALS_FILENAME


def load_credentials(path: Path | None = None) -> CredentialStore:
    """Load the credentials store (an empty store if the file does not exist)."""
    target = path or default_credentials_path()
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return CredentialStore()
    return CredentialStore.from_toml(text)


def save_credentials(store: CredentialStore, path: Path | None = None) -> None:
    """Write *store* to disk atomically, restricting the file to the owner where possible."""
    target = path or default_credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / (target.name + ".tmp")
    tmp.write_text(store.to_toml(), encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(tmp, 0o600)  # tokens are secrets; best effort (a no-op on Windows ACLs)
    tmp.replace(target)
