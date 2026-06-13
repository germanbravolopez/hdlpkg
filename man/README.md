# Man page

`hdlpkg.1` is the `hdlpkg(1)` manual page (groff `man(7)` source). It is
**generated** from the live CLI parser so its command/option reference can never
drift from the real CLI; the narrative sections (description, workflow, files,
registries, examples) are curated in the generator.

## View it without installing

```bash
man ./man/hdlpkg.1          # or: man -l man/hdlpkg.1
```

(`man` ships on Linux/macOS. On Windows, use `hdlpkg --help` / the
[user guide](../docs/user_guide.md) instead, or view it under WSL.)

## Install it so `man hdlpkg` works

`pip` does not place man pages on the `MANPATH`, so install it once by hand:

```bash
sudo install -m 0644 man/hdlpkg.1 /usr/local/share/man/man1/hdlpkg.1
sudo mandb            # refresh the man database (Debian/Ubuntu); optional elsewhere
man hdlpkg
```

For a per-user install without `sudo`, copy it under a `MANPATH` entry you own,
e.g. `~/.local/share/man/man1/hdlpkg.1` (ensure `~/.local/share/man` is on your
`MANPATH`).

## Regenerate after a CLI change

```bash
python scripts/gen_manpage.py            # rewrite man/hdlpkg.1
python scripts/gen_manpage.py --check    # CI gate: fail if the committed page is stale
```

The output is deterministic (no embedded timestamp), so `--check` is a reliable
gate. `tests/unit/test_manpage.py` enforces that the committed page is up to date.
