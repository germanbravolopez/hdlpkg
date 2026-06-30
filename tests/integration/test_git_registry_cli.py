"""Integration tests for the Git-backed registry (``git+...`` locations).

A core stored in a Git repository can be resolved/pulled like any other registry, and
the lockfile records ``git+<url>@<commit-sha>`` so a VLNV/version is traceable to the
exact immutable source. These tests stand up a real local **bare** repo (``git+file://``)
and drive the CLI against it -- the git CLI plus a real remote, no network. The clone
cache is redirected with ``HDLPKG_GIT_CACHE`` so nothing touches the user's home.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from hdlpkg import cli
from hdlpkg.exceptions import RegistryError
from hdlpkg.registry import GitRegistry
from hdlpkg.vlnv import PackageRef

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("git") is None, reason="git CLI not available"),
]

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _git(*args: str, cwd: Path) -> str:
    ident = ["-c", "user.email=t@example.com", "-c", "user.name=Test"]
    out = subprocess.run(
        ["git", *ident, *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


class _Repo:
    """A bare git registry plus the commits the tests pin against."""

    def __init__(self, location: str, head: str, tag_commit: str) -> None:
        self.location = location  # git+file://.../reg.git
        self.head = head  # latest commit on the default branch
        self.tag_commit = tag_commit  # commit the 'v1' tag points at (an earlier one)


def _init_bare(bare: Path) -> None:
    """Create a bare repo, skipping when the environment blocks git in %TEMP%."""
    result = subprocess.run(
        ["git", "init", "--quiet", "--bare", str(bare)], capture_output=True, text=True
    )
    if result.returncode != 0:
        detail = result.stderr.strip()
        if "Permission denied" in detail or "cannot chdir" in detail:
            # Controlled Folder Access / AV denies git operating in %TEMP% on some
            # Windows setups (same gotcha that skips the chdir tests). CI runs this.
            pytest.skip(f"git cannot operate in the temp dir on this environment: {detail}")
        raise RuntimeError(f"git init --bare failed: {detail}")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Repo]:
    monkeypatch.setenv("HDLPKG_GIT_CACHE", str(tmp_path / "gitcache"))
    bare = tmp_path / "reg.git"
    _init_bare(bare)
    work = tmp_path / "seed"
    subprocess.run(["git", "clone", "--quiet", str(bare), str(work)], check=True)
    shutil.copytree(EXAMPLES / "fifo", work / "fifo")
    _git("add", "-A", cwd=work)
    _git("commit", "--quiet", "-m", "publish fifo", cwd=work)
    _git("tag", "v1", cwd=work)
    tag_commit = _git("rev-parse", "HEAD", cwd=work)
    # A *tag* named 'shared' at the early commit; a *branch* of the same name will point
    # at the later HEAD -- the resolver must prefer the immutable tag (A1).
    _git("tag", "shared", cwd=work)
    _git("commit", "--quiet", "--allow-empty", "-m", "later work", cwd=work)
    head = _git("rev-parse", "HEAD", cwd=work)
    _git("branch", "shared", cwd=work)  # branch tip = head, distinct from the 'shared' tag
    _git("push", "--quiet", "--tags", "origin", "HEAD", cwd=work)
    _git("push", "--quiet", "origin", "refs/heads/shared", cwd=work)  # explicit: tag+branch clash
    yield _Repo(f"git+{bare.as_uri()}", head, tag_commit)


def test_resolve_records_git_commit_provenance(repo: _Repo, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    manifest = project / "ip.toml"
    shutil.copy(EXAMPLES / "uart" / "ip.toml", manifest)  # depends on acme:common:fifo

    assert cli.main(["resolve", str(manifest), "--registry", repo.location]) == 0
    lock = (project / "ip.lock").read_text(encoding="utf-8")
    assert "acme:common:fifo:1.0.0" in lock
    # Provenance pins the dependency to the exact default-branch commit.
    assert f"@{repo.head}" in lock


def test_pull_core_from_git_registry(repo: _Repo, tmp_path: Path) -> None:
    rc = cli.main(
        [
            "pull",
            "acme:common:fifo:1.0.0",
            "--registry",
            repo.location,
            "--cache-dir",
            str(tmp_path / "c"),
            "--output",
            str(tmp_path / "fifo"),
        ]
    )
    assert rc == 0
    assert (tmp_path / "fifo" / "ip.toml").is_file()
    assert (tmp_path / "fifo" / "rtl" / "sync_fifo.sv").is_file()


def test_git_registry_checks_out_requested_ref(repo: _Repo, tmp_path: Path) -> None:
    head_reg = GitRegistry(repo.location, cache_root=tmp_path / "a")
    tagged_reg = GitRegistry(f"{repo.location}@v1", cache_root=tmp_path / "b")
    assert head_reg.commit == repo.head
    assert tagged_reg.commit == repo.tag_commit
    assert head_reg.commit != tagged_reg.commit  # the ref selected an earlier commit
    # Both commits still carry the FIFO core.
    assert tagged_reg.versions(PackageRef("acme", "common", "fifo"))


def test_unknown_git_ref_raises(repo: _Repo, tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="not found"):
        GitRegistry(f"{repo.location}@no-such-ref", cache_root=tmp_path / "x")


def test_ref_prefers_tag_over_same_named_branch(repo: _Repo, tmp_path: Path) -> None:
    # 'shared' exists both as a tag (early commit) and a branch (HEAD); the immutable
    # tag must win, so provenance binds to what the user pinned (A1).
    reg = GitRegistry(f"{repo.location}@shared", cache_root=tmp_path / "s")
    assert reg.commit == repo.tag_commit
    assert reg.commit != repo.head


def test_ref_with_a_slash_resolves_a_feature_branch(repo: _Repo, tmp_path: Path) -> None:
    # A git-flow branch name contains '/': pinning @feature/extra must keep the ref whole
    # (the parser locates the '@' in the URL path, not the final segment), so the core is
    # served from that branch rather than the default one.
    work = tmp_path / "feat-seed"
    subprocess.run(["git", "clone", "--quiet", str(tmp_path / "reg.git"), str(work)], check=True)
    _git("checkout", "--quiet", "-b", "feature/extra", cwd=work)
    _git("commit", "--quiet", "--allow-empty", "-m", "feature work", cwd=work)
    feat_head = _git("rev-parse", "HEAD", cwd=work)
    _git("push", "--quiet", "origin", "refs/heads/feature/extra", cwd=work)

    reg = GitRegistry(f"{repo.location}@feature/extra", cache_root=tmp_path / "f")
    assert reg.commit == feat_head
    assert reg.commit != repo.head  # the feature branch is ahead of the default branch
    assert reg.versions(PackageRef("acme", "common", "fifo"))  # core discoverable on it


def test_pinned_sha_resolves_offline_without_fetching(repo: _Repo, tmp_path: Path) -> None:
    # First sync populates the clone cache (tmp_path is shared with the fixture, so the
    # bare repo is tmp_path/reg.git).
    cache = tmp_path / "cache"
    GitRegistry(f"{repo.location}@{repo.head}", cache_root=cache)

    # Make the remote unreachable: an exact-SHA pin already in the clone must still resolve
    # with no network fetch (A4 -- the offline-after-install promise). A branch/tag pin
    # would fail here, proving the fetch was genuinely skipped.
    def _force_rm(func: object, path: str, _exc: object) -> None:
        os.chmod(path, stat.S_IWRITE)  # git pack files are read-only on Windows
        func(path)  # type: ignore[operator]

    shutil.rmtree(tmp_path / "reg.git", onerror=_force_rm)
    reg = GitRegistry(f"{repo.location}@{repo.head}", cache_root=cache)
    assert reg.commit == repo.head
    assert reg.versions(PackageRef("acme", "common", "fifo"))
