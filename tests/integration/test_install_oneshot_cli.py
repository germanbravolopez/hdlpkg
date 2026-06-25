"""Integration tests: ``hdlpkg install <vlnv>`` one-shot (declare + resolve + lock + cache).

Phase 3 of the multi-registry consumer flow: ``install`` accepts dependency specs as well
as (or instead of) a manifest path. A ``vendor:library:name[@constraint]`` argument is added
to the manifest, then the normal resolve + lock + cache runs -- the ``pip install <name>``
experience. ``gen`` (build) stays a separate step.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hdlpkg import cli
from hdlpkg.manifest import Manifest

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A bare consumer manifest (no dependencies yet) in its own directory."""
    proj = tmp_path / "proj"
    proj.mkdir()
    assert cli.main(["init", str(proj), "--vendor", "me", "--library", "soc", "--name", "top"]) == 0
    return proj / "ip.toml"


@pytest.fixture
def store(tmp_path: Path) -> Path:
    location = tmp_path / "store"
    assert (
        cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", str(location)]) == 0
    )
    return location


def test_install_vlnv_adds_the_dependency_then_resolves_and_caches(
    project: Path, store: Path, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    rc = cli.main(
        [
            "install",
            str(project),
            "acme:common:fifo@^1.0.0",
            "--registry",
            str(store),
            "--cache-dir",
            str(cache),
        ]
    )
    assert rc == 0
    # The dependency was written into the manifest...
    manifest = Manifest.from_path(project)
    assert any(str(dep.ref) == "acme:common:fifo" for dep in manifest.dependencies)
    # ...a lockfile was produced...
    assert (project.parent / "ip.lock").is_file()
    # ...and the artifact landed in the cache.
    assert any(cache.rglob("*")) if cache.exists() else False


def test_install_defaults_to_ip_toml_in_the_cwd(
    project: Path, store: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(project.parent)
    rc = cli.main(
        [
            "install",
            "acme:common:fifo",
            "--registry",
            str(store),
            "--cache-dir",
            str(tmp_path / "c"),
        ]
    )
    assert rc == 0
    assert any(
        str(dep.ref) == "acme:common:fifo" for dep in Manifest.from_path(project).dependencies
    )


def test_install_rejects_adding_dependencies_with_locked(project: Path, tmp_path: Path) -> None:
    rc = cli.main(["install", str(project), "acme:common:fifo", "--locked"])
    assert rc != 0


def test_install_rejects_two_manifest_paths(project: Path) -> None:
    other = project.parent / "other.toml"
    shutil.copy(project, other)
    rc = cli.main(["install", str(project), str(other)])
    assert rc != 0


def test_install_self_dependency_is_rejected(project: Path) -> None:
    rc = cli.main(["install", str(project), "me:soc:top"])
    assert rc != 0
