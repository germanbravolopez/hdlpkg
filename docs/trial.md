# Try hdlpkg (feedback welcome)

`hdlpkg` is **pre-1.0 and iterating**: it ships a steady stream of `0.x` capability
releases, and the `ip.toml` / `ip.lock` / CLI shapes can still improve while we are there.
That makes this the best possible time to try it on a real core and tell us what breaks or
feels wrong — format and CLI feedback is cheap to act on now, and steers the next release.

This page is the short brief; the [user guide](user_guide.md) has the full how-to.

## What we are asking

Install the current release, publish a core and consume it from a **different**
machine/account over a registry, and report anything surprising. The point is to validate
the producer -> consumer story end to end with someone who did *not* build the tool.

## 1. Install

Python 3.11+:

```bash
pip install hdlpkg
hdlpkg --version
# if 'hdlpkg' is not on PATH: python -m hdlpkg --version
```

## 2. A 5-minute smoke test (no registry needed)

```bash
hdlpkg init --vendor you --library demo --name widget   # scaffold a core
hdlpkg validate ip.toml
hdlpkg resolve  ip.toml                                  # writes ip.lock
hdlpkg gen sim  ip.toml --output build/sim               # generates Verilator inputs
```

## 3. The real trial: publish and consume over a registry

Stand up a real OCI registry in one command (no auth, for the trial):

```bash
docker run -d -p 5000:5000 --name reg registry:2          # or a Zot binary
```

**As the producer**, publish a core:

```bash
hdlpkg publish ip.toml --registry oci+http://127.0.0.1:5000/ip
```

**As the consumer** (ideally a different person/machine — point at the producer's
registry host instead of localhost), declare a dependency on that core and:

```bash
hdlpkg resolve my_project/ip.toml --registry oci+http://<registry-host>:5000/ip
hdlpkg install my_project/ip.toml --registry oci+http://<registry-host>:5000/ip --locked
hdlpkg pull  you:demo:widget:0.1.0  --registry oci+http://<registry-host>:5000/ip --output ./widget
```

To tear the registry down again:
```bash
docker rm -f reg
```

A **Git repository** of cores also works as a registry — point `--registry` at a
`git+ssh://` / `git+https://` URL (optionally `@<ref>`); see the user guide. For a
**private** registry, `hdlpkg login <location>` first (add `--username` for a registry that
uses the OCI token-exchange). See the user guide's
[*Sharing over a registry*](user_guide.md#sharing-over-a-registry-local-http-or-oci)
section.

## What we most want to hear

While the project is still `0.x`, feedback on the things that will eventually freeze at
`1.0` is the most valuable — it is far cheaper to change them now:

- **The `ip.toml` format** — is anything awkward, missing, or surprising to author?
- **The `ip.lock` format** — does committing and consuming it behave as you expect?
- **The CLI** — command/flag names, error messages, anything that made you guess.
- **The registry protocol / `login`** — did publish/consume across two parties work,
  including against your own registry (Harbor/Artifactory/Zot/GitLab/cloud or a Git repo)?
- Anything that **crashed**, gave a confusing error, or did the wrong thing.

A successful "someone else published, I consumed it" is itself the signal we need.

## How to report

Open an issue at
**https://github.com/germanbravolopez/hdlpkg/issues** — include your OS, Python
version, the exact command, and the full output. Format or protocol friction is especially
worth raising **while we are pre-1.0**: it is much easier to fix before the formats settle
than after.

Thank you — this kind of outside validation is exactly what shapes each release.
