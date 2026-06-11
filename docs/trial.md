# Third-party trial (1.0.0-rc.1)

We are about to finalize **`1.0.0`** — the first stable release, which commits us to the
on-disk formats (`ip.toml`, `ip.lock`), the `hdlpkg` CLI surface, and the registry
protocol. Before we make that promise, we are running a **soak** on the release
candidate `1.0.0-rc.1` and would love an outside pair of hands to try it and tell us
what breaks or feels wrong.

This page is the short brief; the [user guide](user_guide.md) has the full how-to.

## What we are asking

Install the candidate, publish a core and consume it from a **different** machine/account
over a registry, and report anything surprising. The point is to validate the
producer -> consumer story end to end with someone who did *not* build the tool.

## 1. Install the release candidate

`pip` skips pre-releases by default, so ask for it explicitly (Python 3.11+):

```bash
pip install --pre hdl-ip-packager        # or: pip install hdl-ip-packager==1.0.0rc1
hdlpkg --version                          # expect: hdlpkg 1.0.0-rc.1
# if 'hdlpkg' is not on PATH: python -m hdl_ip_packager --version
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

For a **private** registry, `hdlpkg login <location>` first (add `--username` for a
registry that uses the OCI token-exchange). See the user guide's
[*Sharing over a registry*](user_guide.md#sharing-over-a-registry-local-http-or-oci)
section.

## What we most want to hear

Because `1.0.0` freezes these, feedback on them is the most valuable:

- **The `ip.toml` format** — is anything awkward, missing, or surprising to author?
- **The `ip.lock` format** — does committing and consuming it behave as you expect?
- **The CLI** — command/flag names, error messages, anything that made you guess.
- **The registry protocol / `login`** — did publish/consume across two parties work,
  including against your own registry (Harbor/Artifactory/Zot/GitLab/cloud)?
- Anything that **crashed**, gave a confusing error, or did the wrong thing.

A successful "someone else published, I consumed it" is itself the signal we need.

## How to report

Open an issue (or comment on the rc tracking issue) at
**https://github.com/germanbravolopez/hdl-ip-packager/issues** — include your OS, Python
version, the exact command, and the full output. Format or protocol problems are
especially important to raise **now**: fixing one resets the soak (and ships as `0.9.0`
rather than `1.0.0`), so we would much rather hear it before the final cut than after.

Thank you — this is exactly the validation that lets us stand behind `1.0.0`.
