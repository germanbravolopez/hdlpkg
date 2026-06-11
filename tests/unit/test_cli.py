"""Unit tests for the hdlpkg CLI.

The CLI is exercised in-process via ``cli.main(argv)`` so no subprocess is needed;
output is captured with pytest's ``capsys``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hdl_ip_packager import __version__, cli
from hdl_ip_packager.manifest import Manifest

pytestmark = pytest.mark.unit


def test_no_args_prints_help_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main([])
    assert rc == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_info_reports_manifest(write_manifest, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_manifest()
    rc = cli.main(["info", str(path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "acme:comm:uart:1.2.0" in out
    assert "acme:common:fifo" in out
    assert "rtl" in out and "sim" in out


def test_validate_ok(write_manifest, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_manifest()
    rc = cli.main(["validate", str(path)])
    assert rc == 0
    assert "valid manifest" in capsys.readouterr().out


def test_validate_bad_manifest_returns_one(
    write_manifest, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_manifest('[package]\nvendor="a"\n')  # missing required keys
    rc = cli.main(["validate", str(path)])
    assert rc == 1
    assert "error:" in capsys.readouterr().err


def test_missing_manifest_file_returns_one(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["info", "definitely_not_here.toml"])
    assert rc == 1
    assert "error:" in capsys.readouterr().err


def test_init_creates_valid_manifest(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(
        ["init", str(tmp_path), "--vendor", "acme", "--library", "common", "--name", "fifo"]
    )
    assert rc == 0
    assert "Created" in capsys.readouterr().out
    manifest_path = tmp_path / "ip.toml"
    assert manifest_path.exists()
    # The scaffolded manifest must itself validate.
    assert cli.main(["validate", str(manifest_path)]) == 0


def test_init_with_scheme_accepts_a_vendor_version(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main(
        [
            "init",
            str(tmp_path),
            "--vendor",
            "acme",
            "--library",
            "common",
            "--name",
            "fifo",
            "--version",
            "D5020204",
            "--scheme",
            "opaque",
        ]
    )
    assert rc == 0
    manifest_path = tmp_path / "ip.toml"
    assert 'scheme      = "opaque"' in manifest_path.read_text(encoding="utf-8")
    # The scaffolded non-SemVer manifest must itself validate.
    assert cli.main(["validate", str(manifest_path)]) == 0


def test_init_rejects_unknown_scheme(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(
            [
                "init",
                str(tmp_path),
                "--vendor",
                "a",
                "--library",
                "b",
                "--name",
                "c",
                "--scheme",
                "bogus",
            ]
        )
    assert not (tmp_path / "ip.toml").exists()


def test_init_refuses_overwrite_without_force(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "ip.toml").write_text("existing", encoding="utf-8")
    rc = cli.main(["init", str(tmp_path), "--vendor", "a", "--library", "b", "--name", "c"])
    assert rc == 1
    assert "already exists" in capsys.readouterr().err
    # The pre-existing file is left untouched.
    assert (tmp_path / "ip.toml").read_text(encoding="utf-8") == "existing"


def test_init_force_overwrites(tmp_path) -> None:
    (tmp_path / "ip.toml").write_text("existing", encoding="utf-8")
    rc = cli.main(
        ["init", str(tmp_path), "--vendor", "a", "--library", "b", "--name", "c", "--force"]
    )
    assert rc == 0
    assert "existing" not in (tmp_path / "ip.toml").read_text(encoding="utf-8")


def test_init_missing_required_field_returns_one(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Non-interactive (captured stdin) with no --name: fails instead of hanging.
    rc = cli.main(["init", str(tmp_path), "--vendor", "a", "--library", "b"])
    assert rc == 1
    assert "error:" in capsys.readouterr().err
    assert not (tmp_path / "ip.toml").exists()


def test_init_prompts_for_required_fields_when_interactive(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    answers = iter(["acme", "common", "fifo"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    rc = cli.main(["init", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "ip.toml").exists()


def test_init_interactive_blank_answer_still_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    rc = cli.main(["init", str(tmp_path)])
    assert rc == 1
    assert not (tmp_path / "ip.toml").exists()


def test_add_inserts_dependency(tmp_path: Path) -> None:
    manifest = tmp_path / "ip.toml"
    manifest.write_text(
        '[package]\nvendor="acme"\nlibrary="comm"\nname="uart"\nversion="1.0.0"\n',
        encoding="utf-8",
    )
    rc = cli.main(["add", "acme:common:fifo@^1.0.0", str(manifest)])
    assert rc == 0
    reparsed = Manifest.from_path(manifest)
    deps = {str(d.ref): str(d.constraint) for d in reparsed.dependencies}
    assert deps == {"acme:common:fifo": "^1.0.0"}


def test_add_rejects_self_dependency(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = tmp_path / "ip.toml"
    manifest.write_text(
        '[package]\nvendor="acme"\nlibrary="comm"\nname="uart"\nversion="1.0.0"\n',
        encoding="utf-8",
    )
    rc = cli.main(["add", "acme:comm:uart@^1.0.0", str(manifest)])
    assert rc == 1
    assert "cannot depend on itself" in capsys.readouterr().err


def test_build_parser_is_constructable() -> None:
    parser = cli.build_parser()
    assert parser.prog == "hdlpkg"
