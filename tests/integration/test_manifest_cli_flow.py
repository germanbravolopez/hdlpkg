"""Integration test: a manifest on disk flows through the CLI end to end.

Marked ``integration`` (it touches the filesystem and crosses module boundaries:
CLI -> Manifest -> Version/Vlnv). Run only these with ``pytest -m integration``;
exclude them from the fast loop with ``pytest -m 'not integration'``.
"""

from __future__ import annotations

import pytest

from hdl_ip_packager import cli
from hdl_ip_packager.manifest import MANIFEST_FILENAME, Manifest

pytestmark = pytest.mark.integration

MINIMAL = '[package]\nvendor="a"\nlibrary="b"\nname="c"\nversion="0.1.0"\n'


def test_default_manifest_path_is_ip_toml() -> None:
    # `hdlpkg info` with no path argument defaults to ./ip.toml.
    args = cli.build_parser().parse_args(["info"])
    assert args.path == MANIFEST_FILENAME


def test_info_runs_from_within_a_core_directory(tmp_path, monkeypatch, capsys) -> None:
    (tmp_path / MANIFEST_FILENAME).write_text(MINIMAL, encoding="utf-8")
    try:
        monkeypatch.chdir(tmp_path)
    except PermissionError:
        # Some Windows setups (Controlled Folder Access / AV) deny chdir into
        # %TEMP%; the cwd-discovery behaviour is still covered by the default-path
        # test above. Skip rather than fail on such machines.
        pytest.skip("chdir into the temp dir is blocked by this environment")
    rc = cli.main(["info"])
    assert rc == 0
    assert "a:b:c:0.1.0" in capsys.readouterr().out


def test_written_manifest_reparses_identically(write_manifest) -> None:
    path = write_manifest()
    first = Manifest.from_path(path)
    second = Manifest.from_path(path)
    assert first.vlnv == second.vlnv
    assert {str(d.ref) for d in first.dependencies} == {str(d.ref) for d in second.dependencies}
