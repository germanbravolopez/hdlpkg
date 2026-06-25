"""Integration tests: ``hdlpkg vendor`` materializing locked deps into a source tree.

Phase 4 of the multi-registry consumer flow: the content-addressed cache holds ``.ipkg``
blobs, not loose source, so a Makefile cannot read it. ``vendor`` extracts every locked
dependency into a predictable ``<DIR>/<vendor>/<library>/<name>/`` tree -- the node_modules
of HDL -- so an existing Makefile can include the sources.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hdlpkg import cli

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def uart_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    shutil.copy(EXAMPLES / "uart" / "ip.toml", proj / "ip.toml")
    return proj / "ip.toml"


@pytest.fixture
def store(tmp_path: Path) -> Path:
    location = tmp_path / "store"
    assert (
        cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", str(location)]) == 0
    )
    return location


def test_vendor_extracts_locked_deps_into_a_predictable_tree(
    uart_project: Path, store: Path, tmp_path: Path
) -> None:
    assert cli.main(["resolve", str(uart_project), "--registry", str(store)]) == 0
    out = tmp_path / "vendored"

    rc = cli.main(
        [
            "vendor",
            str(uart_project),
            "--output",
            str(out),
            "--cache-dir",
            str(tmp_path / "cache"),
        ]
    )
    assert rc == 0
    # acme:common:fifo -> <out>/acme/common/fifo/ with its RTL present.
    core_dir = out / "acme" / "common" / "fifo"
    assert core_dir.is_dir()
    assert any(core_dir.rglob("sync_fifo.sv"))


def test_vendor_defaults_to_a_deps_dir_next_to_the_manifest(
    uart_project: Path, store: Path, tmp_path: Path
) -> None:
    assert cli.main(["resolve", str(uart_project), "--registry", str(store)]) == 0
    rc = cli.main(["vendor", str(uart_project), "--cache-dir", str(tmp_path / "cache")])
    assert rc == 0
    assert (uart_project.parent / "deps" / "acme" / "common" / "fifo").is_dir()


def test_vendor_replaces_a_stale_tree(uart_project: Path, store: Path, tmp_path: Path) -> None:
    assert cli.main(["resolve", str(uart_project), "--registry", str(store)]) == 0
    out = tmp_path / "vendored"
    cache = str(tmp_path / "cache")
    assert cli.main(["vendor", str(uart_project), "--output", str(out), "--cache-dir", cache]) == 0
    stale = out / "acme" / "common" / "fifo" / "stale.txt"
    stale.write_text("old", encoding="utf-8")

    assert cli.main(["vendor", str(uart_project), "--output", str(out), "--cache-dir", cache]) == 0
    assert not stale.exists()  # the stale file was cleared on re-vendor


def test_vendor_requires_a_lockfile(uart_project: Path, tmp_path: Path) -> None:
    rc = cli.main(["vendor", str(uart_project), "--output", str(tmp_path / "v")])
    assert rc != 0  # no ip.lock -> actionable error


def test_vendor_works_offline_from_the_recorded_source(
    uart_project: Path, store: Path, tmp_path: Path
) -> None:
    # Resolve records source = registry:<store>; vendor with no --registry uses it.
    assert cli.main(["resolve", str(uart_project), "--registry", str(store)]) == 0
    rc = cli.main(
        [
            "vendor",
            str(uart_project),
            "--output",
            str(tmp_path / "v"),
            "--cache-dir",
            str(tmp_path / "c"),
        ]
    )
    assert rc == 0
    assert (tmp_path / "v" / "acme" / "common" / "fifo").is_dir()
