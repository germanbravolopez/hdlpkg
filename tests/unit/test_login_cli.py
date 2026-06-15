"""Unit tests for the `hdlpkg login` / `logout` commands (credential storage)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hdlpkg import cli
from hdlpkg.credentials import load_credentials

pytestmark = pytest.mark.unit


@pytest.fixture
def creds_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "credentials.toml"
    monkeypatch.setenv("HDLPKG_CREDENTIALS", str(path))
    return path


def test_login_stores_token_then_logout_removes_it(creds_path: Path) -> None:
    assert cli.main(["login", "oci://harbor.corp/ip", "--token", "tok"]) == 0
    assert load_credentials(creds_path).token_for("harbor.corp") == "tok"
    assert cli.main(["logout", "oci://harbor.corp/ip"]) == 0
    assert load_credentials(creds_path).token_for("harbor.corp") is None


def test_login_prompts_when_token_flag_omitted(
    creds_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hdlpkg.cli.getpass.getpass", lambda prompt="": "prompted")
    assert cli.main(["login", "https://reg.corp/x"]) == 0
    assert load_credentials(creds_path).token_for("reg.corp") == "prompted"


def test_login_rejects_local_registry(creds_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["login", "/local/dir"]) == 1
    assert "local registry" in capsys.readouterr().err


def test_login_rejects_empty_token(creds_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["login", "oci://harbor.corp/ip", "--token", ""]) == 1
    assert "No token" in capsys.readouterr().err


def test_logout_rejects_local_registry(creds_path: Path) -> None:
    assert cli.main(["logout", "some/dir"]) == 1
