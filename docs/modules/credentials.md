# Credentials — `credentials.py`

Stored bearer tokens for authenticating to **private** registries, so a team can
publish to and consume from a self-hosted HTTP or [OCI](registry.md) registry without
the cores ever being public.

- **Source**: [src/hdl_ip_packager/credentials.py](../../src/hdl_ip_packager/credentials.py)
- **Import**: `from hdl_ip_packager import CredentialStore, load_credentials, save_credentials, registry_host`

## Model

A token is scoped to a **registry host**, not a full URL: `oci://harbor.corp/ip/acme`
and `oci://harbor.corp/ip/dsp` share one token for `harbor.corp`. Local (directory)
registries need no credentials, so their location has no host.

| Symbol | Description |
|--------|-------------|
| `registry_host(location) -> str \| None` | The lowercased `host[:port]` a token applies to, or `None` for a local-path registry. Raises `CredentialsError` if a network URL has no host. |
| `CredentialStore(tokens)` | An immutable map of host -> token. `token_for(host)`, `with_token(host, token)`, `without(host)`, `to_toml()`, `from_toml(text)`. |
| `default_credentials_path()` | `$HDLPKG_CREDENTIALS` or `~/.hdlpkg/credentials.toml`. |
| `load_credentials(path=None)` | Load the store (empty if the file is absent). |
| `save_credentials(store, path=None)` | Write atomically, owner-only (`0o600`) where the OS allows. |

The pure `CredentialStore` does all parsing/serialization and host keying, so the logic
is unit-testable without touching the filesystem; `load`/`save` are the only I/O.

## On-disk format

```toml
[tokens]
"harbor.corp.local" = "tok_..."
"ip.corp.local:8443" = "tok_..."
```

## How it is used

`hdlpkg login <location> [--token]` stores a token (prompting without echo when
`--token` is omitted); `hdlpkg logout <location>` removes it.
[`registry_from_location`](registry.md) reads the store and passes the matching token to
the network backend, which sends `Authorization: Bearer <token>` on every request.
Missing or wrong credentials fail closed.

## Errors

`CredentialsError` — a malformed credentials file, a non-string token, or a network
registry location with no host.

## Example

```python
from hdl_ip_packager import load_credentials, save_credentials, registry_host

host = registry_host("oci://harbor.corp/ip/acme")          # "harbor.corp"
save_credentials(load_credentials().with_token(host, "tok_..."))
token = load_credentials().token_for(host)
```
