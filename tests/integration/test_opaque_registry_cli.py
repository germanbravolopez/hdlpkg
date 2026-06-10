"""Integration test: opaque (non-SemVer) versions through publish + registry resolve.

An opaque-scheme core carries a non-SemVer version token (a vendor part number).
This exercises the full path: publish it to a local registry (stored under a
non-SemVer directory name), then resolve a consumer against that registry and
confirm the lockfile pins the opaque VLNV and round-trips its scheme.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hdl_ip_packager import cli
from hdl_ip_packager.lockfile import Lockfile

pytestmark = pytest.mark.integration


def _core(directory: Path, toml: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ip.toml").write_text(toml, encoding="utf-8")
    (directory / "rtl").mkdir(exist_ok=True)
    (directory / "rtl" / "src.sv").write_text("module m; endmodule\n", encoding="utf-8")


def test_opaque_core_publishes_and_resolves_from_registry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rtl = '\n[filesets.rtl]\nfiles = ["rtl/src.sv"]\ntype = "systemVerilogSource"\n'
    vendor = tmp_path / "radio"
    _core(
        vendor,
        '[package]\nvendor="acme"\nlibrary="rf"\nname="radio"\nversion="D5020100"\n'
        'scheme="opaque"\ntop="radio"\n' + rtl,
    )
    top = tmp_path / "top"
    _core(
        top,
        '[package]\nvendor="acme"\nlibrary="soc"\nname="top"\nversion="1.0.0"\ntop="t"\n'
        '[dependencies]\n"acme:rf:radio" = "=D5020100"\n' + rtl,
    )
    registry = tmp_path / "registry"

    assert cli.main(["publish", str(vendor / "ip.toml"), "--registry", str(registry)]) == 0
    out_lock = tmp_path / "ip.lock"
    rc = cli.main(
        ["resolve", str(top / "ip.toml"), "--registry", str(registry), "--output", str(out_lock)]
    )
    assert rc == 0
    assert "acme:rf:radio:D5020100" in capsys.readouterr().out

    lock = Lockfile.from_path(out_lock)
    assert [str(p.vlnv) for p in lock.packages] == ["acme:rf:radio:D5020100"]
    assert 'scheme   = "opaque"' in out_lock.read_text(encoding="utf-8")

    # pull/yank take a VLNV string with no scheme: the opaque token must still parse.
    cache = tmp_path / "cache"
    pulled = tmp_path / "pulled"
    rc = cli.main(
        [
            "pull",
            "acme:rf:radio:D5020100",
            "--registry",
            str(registry),
            "--cache-dir",
            str(cache),
            "--output",
            str(pulled),
        ]
    )
    assert rc == 0
    assert (pulled / "ip.toml").is_file()
