"""Integration test: the bundled example cores under ``examples/`` are valid.

The example cores (a FIFO and a UART that depends on it) exist to drive the docs
and end-to-end tests against *real* manifests on disk rather than inline fixtures.
This suite guards three properties, all enforced in CI:

1. Every ``examples/*/ip.toml`` parses and validates (``Manifest`` + the
   ``hdlpkg validate`` CLI path).
2. Every file a fileset references actually exists on disk relative to its core
   root - no dangling source paths.
3. The example dependency graph is self-contained: each dependency on an example
   (``acme``) core points at another example core that ships in this tree.

Marked ``integration`` (it touches the filesystem and crosses module boundaries:
CLI -> Manifest -> Version/Vlnv).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hdlpkg import cli
from hdlpkg.manifest import MANIFEST_FILENAME, Manifest

pytestmark = pytest.mark.integration

# Repo root is two levels up from tests/integration/.
EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"

# Vendor used by the bundled examples; only deps on this vendor must ship locally.
EXAMPLE_VENDOR = "acme"


def _example_manifests() -> list[Path]:
    return sorted(EXAMPLES_DIR.glob(f"*/{MANIFEST_FILENAME}"))


def test_examples_directory_has_manifests() -> None:
    assert EXAMPLES_DIR.is_dir(), f"missing examples directory: {EXAMPLES_DIR}"
    assert _example_manifests(), f"no example {MANIFEST_FILENAME} manifests found"


@pytest.mark.parametrize("manifest_path", _example_manifests(), ids=lambda p: p.parent.name)
def test_example_manifest_validates(manifest_path: Path, capsys) -> None:
    manifest = Manifest.from_path(manifest_path)  # raises ManifestError on failure
    assert cli.main(["validate", str(manifest_path)]) == 0
    assert str(manifest.vlnv) in capsys.readouterr().out


@pytest.mark.parametrize("manifest_path", _example_manifests(), ids=lambda p: p.parent.name)
def test_example_fileset_files_exist(manifest_path: Path) -> None:
    root = manifest_path.parent
    manifest = Manifest.from_path(manifest_path)
    missing = [
        rel
        for fileset in manifest.filesets.values()
        for rel in fileset.files
        if not (root / rel).is_file()
    ]
    assert not missing, f"{root.name}: fileset references missing files {missing}"


def test_example_dependencies_resolve_within_the_tree() -> None:
    manifests = [Manifest.from_path(p) for p in _example_manifests()]
    available = {m.ref for m in manifests}
    for manifest in manifests:
        for dep in manifest.dependencies:
            if dep.ref.vendor == EXAMPLE_VENDOR:
                assert dep.ref in available, (
                    f"{manifest.vlnv} depends on {dep.ref}, which is not a bundled example core"
                )
