"""Integration tests for the conflict-resolution policy end to end (``hdlpkg``).

Builds the demo's incompatible scenario in a temp tree -- ``fifo`` needs
``bus ^1`` and ``legacy`` needs ``bus ^2`` -- and exercises each
``[resolution] on-conflict`` policy through the CLI, plus ``gen`` name-mangling two
coexisting module versions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hdlpkg import cli

pytestmark = pytest.mark.integration


def _core(directory: Path, toml: str, module: str = "m") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ip.toml").write_text(toml, encoding="utf-8")
    (directory / "rtl").mkdir(exist_ok=True)
    (directory / "rtl" / "src.sv").write_text(f"module {module}; endmodule\n", encoding="utf-8")


def _scenario(root: Path, *, policy: str | None = None) -> Path:
    """Lay out bus 1.0/1.1/2.0, fifo (bus ^1), legacy (bus ^2), and a top, return top dir."""
    rtl = '\n[filesets.rtl]\nfiles = ["rtl/src.sv"]\ntype = "systemVerilogSource"\n'
    for version in ("1.0.0", "1.1.0", "2.0.0"):
        _core(
            root / f"bus-{version}",
            f'[package]\nvendor="acme"\nlibrary="common"\nname="bus"\nversion="{version}"\n' + rtl,
            module="bus",
        )
    _core(
        root / "fifo",
        '[package]\nvendor="acme"\nlibrary="ip"\nname="fifo"\nversion="1.0.0"\n'
        '[dependencies]\n"acme:common:bus" = "^1.0.0"\n' + rtl,
        module="fifo",
    )
    _core(
        root / "legacy",
        '[package]\nvendor="acme"\nlibrary="ip"\nname="legacy"\nversion="1.0.0"\n'
        '[dependencies]\n"acme:common:bus" = "^2.0.0"\n' + rtl,
        module="legacy",
    )
    resolution = f'[resolution]\non-conflict = "{policy}"\n' if policy else ""
    top = root / "top"
    _core(
        top,
        '[package]\nvendor="acme"\nlibrary="soc"\nname="top"\nversion="1.0.0"\ntop="top"\n'
        '[dependencies]\n"acme:ip:fifo" = "^1.0.0"\n"acme:ip:legacy" = "^1.0.0"\n'
        + resolution
        + '\n[filesets.rtl]\nfiles = ["rtl/src.sv"]\ntype = "systemVerilogSource"\n'
        '[targets.synth]\ntoolflow = "vivado"\nfilesets = ["rtl"]\n',
        module="top",
    )
    return top


def test_default_policy_fails_on_incompatible_conflict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    top = _scenario(tmp_path)
    rc = cli.main(["resolve", str(top / "ip.toml"), "--search", str(tmp_path)])
    assert rc == 1
    assert "incompatible versions" in capsys.readouterr().err


def test_cli_override_isolates_and_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    top = _scenario(tmp_path)
    output = tmp_path / "ip.lock"
    rc = cli.main(
        [
            "resolve",
            str(top / "ip.toml"),
            "--search",
            str(tmp_path),
            "--output",
            str(output),
            "--on-conflict",
            "isolate_namespaces",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "acme:common:bus:1.1.0" in captured.out
    assert "acme:common:bus:2.0.0" in captured.out
    assert "isolate_namespaces" in captured.err  # the warning goes to stderr


def test_manifest_policy_use_latest_collapses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    top = _scenario(tmp_path, policy="use_latest")
    output = tmp_path / "ip.lock"
    rc = cli.main(
        ["resolve", str(top / "ip.toml"), "--search", str(tmp_path), "--output", str(output)]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "acme:common:bus:2.0.0" in captured.out
    assert "acme:common:bus:1.1.0" not in captured.out  # collapsed away
    assert "use_latest" in captured.err


def test_gen_mangles_two_module_versions(tmp_path: Path) -> None:
    # Under isolate_namespaces the two `module bus` versions coexist: gen now name-mangles
    # them (it no longer refuses module coexistence).
    top = _scenario(tmp_path, policy="isolate_namespaces")
    out = tmp_path / "build"
    rc = cli.main(
        ["gen", "synth", str(top / "ip.toml"), "--search", str(tmp_path), "--output", str(out)]
    )
    assert rc == 0
    text = "\n".join(p.read_text(encoding="utf-8") for p in (out / "src").rglob("*.sv"))
    assert "module bus_v1_1_0;" in text
    assert "module bus_v2_0_0;" in text
