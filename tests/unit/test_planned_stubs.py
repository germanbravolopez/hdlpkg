"""Smoke tests for the planned subsystems (resolver, registry).

These modules are intentionally unimplemented, but they are part of the public
package surface and their interfaces must import cleanly and fail loudly. Testing
that contract now keeps the seams honest and counts them in coverage.
"""

from __future__ import annotations

import pytest

from hdl_ip_packager import registry, resolver
from hdl_ip_packager.manifest import Manifest

pytestmark = pytest.mark.unit


def test_resolve_is_not_implemented_yet(sample_manifest_toml: str) -> None:
    manifest = Manifest.from_str(sample_manifest_toml)
    with pytest.raises(NotImplementedError):
        resolver.resolve(manifest, {})


def test_registry_is_abstract() -> None:
    # The abstract base cannot be instantiated until a concrete backend exists.
    with pytest.raises(TypeError):
        registry.Registry()  # type: ignore[abstract]
