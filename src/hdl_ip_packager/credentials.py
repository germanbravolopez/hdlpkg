"""Stored credentials for authenticating to private registries.

Network registries (HTTP, OCI) backing a company's *private* IP sharing require a
credential to read or publish. ``hdlpkg login <registry>`` stores a per-host
:class:`Credential` in a user file; ``resolve`` / ``install`` / ``publish`` read it
back automatically, so a team consumes from an internal registry without the cores
ever being public.

A credential is scoped to a **registry host**, not a full URL: ``oci://harbor.corp/ip/a``
and ``oci://harbor.corp/ip/b`` share the one credential for ``harbor.corp``. Local
(directory) registries need no credentials, so their location has no host.

A credential is a *secret* plus an optional *username*:

* a **bearer token** alone (``username is None``) -- presented directly as
  ``Authorization: Bearer <secret>`` (what a self-hosted Harbor/Zot accepts), and
* a **username + secret** (password or robot token) -- used as HTTP Basic credentials
  in the OCI *token-exchange* flow that managed registries require (see ``registry.py``).

As a convenience, credentials a user already has from ``docker login`` are reused:
:func:`load_docker_config` reads ``~/.docker/config.json`` so a host present there
works without a separate ``hdlpkg login``.

Design: the pure :class:`CredentialStore` / :class:`Credential` value types and the
parsers do all logic, so they are unit-testable without I/O; the thin
:func:`load_credentials` / :func:`save_credentials` / :func:`load_docker_config` are
the only filesystem access. The store is TOML at ``~/.hdlpkg/credentials.toml``
(override with ``HDLPKG_CREDENTIALS``).
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .cache import DEFAULT_CACHE_DIRNAME
from .exceptions import CredentialsError

__all__ = [
    "CREDENTIALS_ENV_VAR",
    "Credential",
    "CredentialStore",
    "default_credentials_path",
    "load_credentials",
    "load_docker_config",
    "parse_docker_config",
    "registry_host",
    "save_credentials",
]

CREDENTIALS_ENV_VAR = "HDLPKG_CREDENTIALS"
_CREDENTIALS_FILENAME = "credentials.toml"
_REGISTRIES_TABLE = "registries"
_LEGACY_TOKENS_TABLE = "tokens"
_NETWORK_SCHEMES = ("http", "https", "oci", "oci+http")


def registry_host(location: str) -> str | None:
    """The lowercased host a credential applies to, or ``None`` for a local-path registry.

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


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


@dataclass(frozen=True)
class Credential:
    """A registry secret (bearer token or password) with an optional username."""

    secret: str
    username: str | None = None

    @property
    def is_basic(self) -> bool:
        """True if this carries a username (so it authenticates via HTTP Basic)."""
        return self.username is not None


@dataclass(frozen=True)
class CredentialStore:
    """An immutable map of registry host -> :class:`Credential`."""

    credentials: dict[str, Credential] = field(default_factory=dict)

    def credential_for(self, host: str | None) -> Credential | None:
        """The stored credential for *host* (lowercased), or ``None`` if there is none."""
        if host is None:
            return None
        return self.credentials.get(host.lower())

    def token_for(self, host: str | None) -> str | None:
        """The stored secret for *host* (convenience for direct-bearer callers)."""
        credential = self.credential_for(host)
        return credential.secret if credential else None

    def with_token(self, host: str, secret: str, username: str | None = None) -> CredentialStore:
        """A copy with *host* set to (secret, username), replacing any existing entry."""
        updated = dict(self.credentials)
        updated[host.lower()] = Credential(secret, username)
        return CredentialStore(updated)

    def without(self, host: str) -> CredentialStore:
        """A copy with *host* removed (idempotent)."""
        updated = dict(self.credentials)
        updated.pop(host.lower(), None)
        return CredentialStore(updated)

    def with_fallback(self, others: dict[str, Credential]) -> CredentialStore:
        """A copy that adds *others* for hosts not already present (self wins)."""
        merged = {host.lower(): cred for host, cred in others.items()}
        merged.update(self.credentials)
        return CredentialStore(merged)

    def to_toml(self) -> str:
        """Serialize to a deterministic TOML document (hosts sorted)."""
        lines: list[str] = []
        for host in sorted(self.credentials):
            credential = self.credentials[host]
            lines.append(f'[{_REGISTRIES_TABLE}."{_escape(host)}"]')
            lines.append(f'secret = "{_escape(credential.secret)}"')
            if credential.username is not None:
                lines.append(f'username = "{_escape(credential.username)}"')
            lines.append("")
        return "\n".join(lines).rstrip("\n") + "\n" if lines else ""

    @classmethod
    def from_toml(cls, text: str) -> CredentialStore:
        """Parse a credentials document; raise :class:`CredentialsError` if malformed.

        Reads the current ``[registries."host"]`` table form and the legacy
        ``[tokens]`` (host = token) form, so an older file keeps working.
        """
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise CredentialsError(f"Malformed credentials file: {exc}") from exc

        credentials: dict[str, Credential] = {}

        legacy = data.get(_LEGACY_TOKENS_TABLE, {})
        if not isinstance(legacy, dict):
            raise CredentialsError(f"[{_LEGACY_TOKENS_TABLE}] must be a table of host = token.")
        for host, token in legacy.items():
            if not isinstance(token, str):
                raise CredentialsError(f"Token for {host!r} must be a string.")
            credentials[host.lower()] = Credential(token)

        registries = data.get(_REGISTRIES_TABLE, {})
        if not isinstance(registries, dict):
            raise CredentialsError(f"[{_REGISTRIES_TABLE}] must be a table of host entries.")
        for host, entry in registries.items():
            if not isinstance(entry, dict) or not isinstance(entry.get("secret"), str):
                raise CredentialsError(f"Registry {host!r} needs a string 'secret'.")
            username = entry.get("username")
            if username is not None and not isinstance(username, str):
                raise CredentialsError(f"Username for {host!r} must be a string.")
            credentials[host.lower()] = Credential(entry["secret"], username)

        return cls(credentials)


def parse_docker_config(data: dict[str, object]) -> dict[str, Credential]:
    """Extract host -> :class:`Credential` from a parsed ``~/.docker/config.json``.

    Reads each ``auths[host]`` entry: a base64 ``user:password`` ``auth`` field becomes
    a Basic credential, and an ``identitytoken`` becomes a bearer credential. Hosts are
    normalized to ``host[:port]`` (a ``scheme://`` prefix or trailing path is stripped).
    Malformed entries are skipped rather than failing the whole load.
    """
    auths = data.get("auths")
    if not isinstance(auths, dict):
        return {}
    found: dict[str, Credential] = {}
    for raw_host, entry in auths.items():
        if not isinstance(entry, dict):
            continue
        host = _normalize_docker_host(str(raw_host))
        identity = entry.get("identitytoken")
        if isinstance(identity, str) and identity:
            found[host] = Credential(identity)
            continue
        auth = entry.get("auth")
        if not isinstance(auth, str) or not auth:
            continue
        try:
            decoded = base64.b64decode(auth).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        username, sep, password = decoded.partition(":")
        if sep:
            found[host] = Credential(password, username)
    return found


def _normalize_docker_host(key: str) -> str:
    """Reduce a docker-config auth key (URL or host) to a lowercased ``host[:port]``."""
    if "://" in key:
        key = urlsplit(key).netloc or key.split("://", 1)[1]
    return key.split("/", 1)[0].lower()


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
        os.chmod(tmp, 0o600)  # secrets; best effort (a no-op on Windows ACLs)
    tmp.replace(target)


def load_docker_config(path: Path | None = None) -> dict[str, Credential]:
    """Read docker's ``config.json`` (``$DOCKER_CONFIG`` or ``~/.docker``); ``{}`` if absent."""
    if path is None:
        base = os.environ.get("DOCKER_CONFIG")
        path = (Path(base) if base else Path.home() / ".docker") / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return parse_docker_config(data) if isinstance(data, dict) else {}
