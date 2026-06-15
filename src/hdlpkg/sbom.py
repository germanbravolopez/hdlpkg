"""Software Bill of Materials (SBOM) generation in CycloneDX format.

An SBOM records exactly what a released artifact contains -- the core itself plus
its (resolved) dependencies -- so a consumer can audit provenance and licences.
We emit **CycloneDX 1.5** JSON, a widely-tooled SBOM standard, at ``pack`` time.

:func:`build_cyclonedx` is **pure**: it maps a root
:class:`~hdlpkg.manifest.Manifest` plus its resolved dependency manifests
to a deterministic JSON string (no I/O, no timestamps, sorted keys and entries), so
the same inputs always produce byte-identical output -- a property an SBOM needs to
be cacheable and diff-able. The CLI ``pack --sbom`` is the thin write wrapper.

Signing the artifact + SBOM (Sigstore/cosign keyless) is the other half of the
supply-chain milestone; it needs OIDC + Fulcio/Rekor infrastructure to do honestly
and is tracked as an open issue. Checksums (the packed-content SHA-256) already pin
integrity across the cache, lockfile, and registry.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from .manifest import Manifest
from .vlnv import Vlnv

__all__ = ["CYCLONEDX_SPEC_VERSION", "build_cyclonedx"]

CYCLONEDX_SPEC_VERSION = "1.5"


def _purl(vlnv: Vlnv) -> str:
    """A package URL (purl) identifier for a core, using the ``generic`` type."""
    return f"pkg:generic/{vlnv.vendor}.{vlnv.library}/{vlnv.name}@{vlnv.version}"


def _component(manifest: Manifest, component_type: str) -> dict[str, object]:
    """Render one manifest as a CycloneDX component."""
    vlnv = manifest.vlnv
    component: dict[str, object] = {
        "type": component_type,
        "bom-ref": str(vlnv),
        "group": f"{vlnv.vendor}.{vlnv.library}",
        "name": vlnv.name,
        "version": str(vlnv.version),
        "purl": _purl(vlnv),
    }
    if manifest.description:
        component["description"] = manifest.description
    if manifest.license:
        component["licenses"] = [{"license": {"id": manifest.license}}]
    return component


def _dependency_edges(root: Manifest, dependencies: Sequence[Manifest]) -> list[dict[str, object]]:
    """Build the CycloneDX ``dependencies`` graph from declared deps -> resolved VLNVs."""
    resolved: Mapping[str, Vlnv] = {str(m.ref): m.vlnv for m in dependencies} | {
        str(root.ref): root.vlnv
    }

    edges: list[dict[str, object]] = []
    for manifest in (root, *dependencies):
        depends_on = sorted(
            str(resolved[str(dep.ref)]) for dep in manifest.dependencies if str(dep.ref) in resolved
        )
        if depends_on:
            edges.append({"ref": str(manifest.vlnv), "dependsOn": depends_on})
    return edges


def build_cyclonedx(root: Manifest, dependencies: Sequence[Manifest] = ()) -> str:
    """Render a deterministic CycloneDX 1.5 SBOM for *root* and its *dependencies*.

    Args:
        root: the core being packaged (the SBOM's top-level component).
        dependencies: the resolved dependency manifests (concrete versions). May be
            empty for a leaf core.

    Returns:
        Pretty-printed, deterministic JSON (sorted keys; components and edges sorted
        by VLNV; no timestamp or random serial number).
    """
    components = [_component(m, "library") for m in sorted(dependencies, key=lambda m: str(m.vlnv))]
    bom: dict[str, object] = {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_SPEC_VERSION,
        "version": 1,
        "metadata": {"component": _component(root, "application")},
        "components": components,
        "dependencies": _dependency_edges(root, dependencies),
    }
    return json.dumps(bom, indent=2, sort_keys=True) + "\n"
