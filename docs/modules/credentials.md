# Credentials — `credentials.py`

Stored credentials for authenticating to **private** registries, so a team can publish
to and consume from a self-hosted HTTP or [OCI](registry.md) registry without the cores
ever being public.

- **Source**: [src/hdl_ip_packager/credentials.py](../../src/hdl_ip_packager/credentials.py)
- **Import**: `from hdl_ip_packager import Credential, CredentialStore, load_credentials, save_credentials, registry_host, load_docker_config`

## Model

A credential is scoped to a **registry host**, not a full URL: `oci://harbor.corp/ip/a`
and `oci://harbor.corp/ip/b` share one credential for `harbor.corp`. Local (directory)
registries need no credentials, so their location has no host.

A `Credential` is a *secret* plus an optional *username*:

- **bearer token** alone (`username is None`) — sent directly as `Authorization: Bearer
  <secret>` (the self-hosted / static-token case);
- **username + secret** (password or robot token) — used as HTTP Basic credentials in the
  OCI [token-exchange](registry.md) flow that managed registries require.

| Symbol | Description |
|--------|-------------|
| `registry_host(location) -> str \| None` | The lowercased `host[:port]` a credential applies to, or `None` for a local-path registry. Raises `CredentialsError` if a network URL has no host. |
| `Credential(secret, username=None)` | A registry secret with an optional username; `.is_basic` is true when a username is set. |
| `CredentialStore(credentials)` | An immutable map host -> `Credential`. `credential_for(host)`, `token_for(host)`, `with_token(host, secret, username=None)`, `without(host)`, `with_fallback(others)`, `to_toml()`, `from_toml(text)`. |
| `default_credentials_path()` | `$HDLPKG_CREDENTIALS` or `~/.hdlpkg/credentials.toml`. |
| `load_credentials(path=None)` / `save_credentials(store, path=None)` | Load / atomically write (owner-only `0o600` where the OS allows). |
| `load_docker_config(path=None)` / `parse_docker_config(data)` | Read `~/.docker/config.json` (`$DOCKER_CONFIG` honored) into host -> `Credential` (base64 `auth` or `identitytoken`), reused as a fallback. |

The pure `CredentialStore` / `Credential` value types and `parse_docker_config` do all
logic, so they are unit-testable without I/O; `load`/`save`/`load_docker_config` are the
only filesystem access.

## On-disk format

```toml
[registries."harbor.corp.local"]
secret = "tok_..."

[registries."reg.corp.local:5000"]
secret = "robot-password"
username = "robot$ci"
```

The legacy `[tokens]` table (`"host" = "token"`) is still read, so an older file keeps
working.

## How it is used

`hdlpkg login <location> [--username U] [--token|--password S]` stores a credential
(prompting without echo when the secret is omitted); `hdlpkg logout <location>` removes
it. [`registry_from_location`](registry.md) reads the store (with `docker login`
credentials merged in as a fallback) and hands the matching credential to the network
backend: HTTP uses the secret as a direct bearer; OCI uses the full credential, presenting
a username-less one directly and driving the token exchange for a username+secret one.
Missing or wrong credentials fail closed.

## Errors

`CredentialsError` — a malformed credentials file, a non-string secret/username, or a
network registry location with no host.

## Example

```python
from hdl_ip_packager import Credential, load_credentials, save_credentials, registry_host

host = registry_host("oci://harbor.corp/ip/acme")          # "harbor.corp"
# a robot account for a managed registry (token-exchange via HTTP Basic):
save_credentials(load_credentials().with_token(host, "robot-pw", username="robot$ci"))
credential = load_credentials().credential_for(host)       # Credential("robot-pw", "robot$ci")
```
