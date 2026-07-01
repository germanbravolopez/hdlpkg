"""Integration test: ``hdlpkg gen <target> --format filelist`` for a Makefile flow.

Emits flat ordered ``.f`` source lists (one per HDL type) of cache paths, so a flow without
a dedicated hdlpkg backend (QuestaSim, Quartus, ...) can compile the IP straight from the
cache -- the dependency sources are materialized under the cache, never vendored into the
project tree.
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
    # Copy the whole core so the root's own RTL/tb exist on disk (the dependency comes from
    # the cache); the filelist then references real, absolute paths.
    proj = tmp_path / "proj"
    shutil.copytree(EXAMPLES / "uart", proj)
    return proj / "ip.toml"


def test_gen_filelist_lists_dependency_then_root_sources_from_the_cache(
    uart_project: Path, tmp_path: Path
) -> None:
    store = tmp_path / "store"
    assert cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", str(store)]) == 0

    cache = tmp_path / "cache"
    out = tmp_path / "out"
    rc = cli.main(
        [
            "gen",
            "sim",
            str(uart_project),
            "--format",
            "filelist",
            "--registry",
            str(store),
            "--cache-dir",
            str(cache),
            "--output",
            str(out),
        ]
    )
    assert rc == 0

    # One ordered .f per HDL type; the uart design is all SystemVerilog.
    filelists = list(out.glob("*.systemverilog.f"))
    assert len(filelists) == 1
    lines = filelists[0].read_text(encoding="utf-8").splitlines()

    # The dependency (fifo) compiles before the root (uart) -- dependencies first.
    fifo_idx = next(i for i, p in enumerate(lines) if p.endswith("sync_fifo.sv"))
    uart_idx = next(i for i, p in enumerate(lines) if p.endswith("uart_top.sv"))
    assert fifo_idx < uart_idx

    # Every path is absolute and the dependency source lives under the cache, not the repo.
    # hdlpkg emits forward-slash paths (portable), so compare in posix form (Windows-safe).
    assert all(Path(p).is_absolute() and Path(p).is_file() for p in lines)
    assert cache.as_posix() in lines[fifo_idx]
    assert uart_project.parent.as_posix() not in lines[fifo_idx]  # IP not vendored into the tree


def test_gen_filelist_is_offline_after_install_locked(uart_project: Path, tmp_path: Path) -> None:
    store = tmp_path / "store"
    assert cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", str(store)]) == 0
    cache = tmp_path / "cache"
    assert cli.main(["resolve", str(uart_project), "--registry", str(store)]) == 0
    assert cli.main(["install", str(uart_project), "--cache-dir", str(cache), "--locked"]) == 0

    # No --registry: the cache (warmed by install --locked) is enough for the filelist.
    rc = cli.main(
        [
            "gen",
            "sim",
            str(uart_project),
            "--format",
            "filelist",
            "--locked",
            "--cache-dir",
            str(cache),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 0
    assert next((tmp_path / "out").glob("*.f"), None) is not None
