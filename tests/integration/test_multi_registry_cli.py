"""Integration tests: multi-registry resolve via repeatable ``--registry`` (CLI order).

A consumer's dependencies may live in different registries. Passing ``--registry`` more
than once builds an ordered search path (a ``CompositeRegistry``): versions are unioned
across registries, and each core is served by the first registry, in order, that has it.
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
    """A temp UART manifest (depends on acme:common:fifo ^1.0.0), isolated from search."""
    proj = tmp_path / "proj"
    proj.mkdir()
    manifest = proj / "ip.toml"
    shutil.copy(EXAMPLES / "uart" / "ip.toml", manifest)
    return manifest


def _publish_fifo(location: Path) -> None:
    fifo = str(EXAMPLES / "fifo" / "ip.toml")
    assert cli.main(["publish", fifo, "--registry", str(location)]) == 0


def test_resolve_finds_a_dependency_in_the_second_registry(
    uart_project: Path, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    store = tmp_path / "store"
    _publish_fifo(store)
    lock = uart_project.parent / "ip.lock"

    rc = cli.main(
        ["resolve", str(uart_project), "--registry", str(empty), "--registry", str(store)]
    )

    assert rc == 0
    text = lock.read_text(encoding="utf-8")
    assert "acme:common:fifo" in text or "fifo" in text
    # The resolved core is pinned to the registry that actually had it (the second one).
    assert str(store) in text


def test_shadowed_vlnv_warns_and_takes_the_first_registry(
    uart_project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _publish_fifo(first)
    _publish_fifo(second)

    rc = cli.main(
        ["resolve", str(uart_project), "--registry", str(first), "--registry", str(second)]
    )

    assert rc == 0
    err = capsys.readouterr().err
    assert "multiple registries" in err
    # First-in-order wins: the lock pins the core to the first registry.
    assert str(first) in (uart_project.parent / "ip.lock").read_text(encoding="utf-8")
