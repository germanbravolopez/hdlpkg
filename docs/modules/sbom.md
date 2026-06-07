# SBOM (CycloneDX) — `sbom.py`

Generate a Software Bill of Materials in CycloneDX format, recording exactly what a
released artifact contains — the core plus its resolved dependencies — for provenance
and licence audit. Pure module.

- **Source**: [src/hdl_ip_packager/sbom.py](../../src/hdl_ip_packager/sbom.py)
- **Import**: `from hdl_ip_packager import build_cyclonedx, CYCLONEDX_SPEC_VERSION`

## API

```python
def build_cyclonedx(root: Manifest, dependencies: Sequence[Manifest] = ()) -> str
CYCLONEDX_SPEC_VERSION   # "1.5"
```

- `root` — the core being packaged (the SBOM's top-level `metadata.component`).
- `dependencies` — the resolved dependency [manifests](manifest.md) (concrete
  versions). May be empty for a leaf core.

## What it produces

A **CycloneDX 1.5** JSON document:

- `metadata.component` — the root core (VLNV `bom-ref`, `group`, `version`, a
  `pkg:generic/…` purl, plus description/licence);
- `components` — one entry per dependency;
- `dependencies` — the edge graph (which component depends on which).

The output is **deterministic by construction**: sorted keys, components and edges
sorted by VLNV, and **no timestamp or random serial number** — so the same inputs
produce byte-identical SBOM bytes (a property an SBOM needs to be cacheable and
diff-able).

## Where it fits (supply chain)

This is the integrity + bill-of-materials half of the supply-chain milestone, on top
of the SHA-256 content addressing that already pins every artifact across the
[cache](cache.md), [lockfile](lockfile.md), and [registry](registry.md). Sigstore
(cosign) **signing** is the remaining half — deferred, as it needs OIDC/Fulcio/Rekor
infrastructure to do honestly.

## Example

```python
from hdl_ip_packager import Manifest, build_cyclonedx

root = Manifest.from_path("examples/uart/ip.toml")
fifo = Manifest.from_path("examples/fifo/ip.toml")
sbom = build_cyclonedx(root, [fifo])   # CycloneDX 1.5 JSON, deterministic
```

`hdlpkg pack --sbom` writes this alongside the `.ipkg`; see [the CLI page](cli.md).
