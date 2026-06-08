"""Unit tests for the lockfile (``ip.lock``) model.

The lockfile module is pure, so these tests build a resolution in memory, then
assert serialization is deterministic, parsing round-trips, and integrity
verification fails closed on a missing or mismatched checksum.
"""

from __future__ import annotations

import pytest

from hdl_ip_packager.exceptions import LockfileError
from hdl_ip_packager.lockfile import (
    LOCKFILE_VERSION,
    LockedPackage,
    Lockfile,
    sha256_digest,
)
from hdl_ip_packager.resolver import Resolution
from hdl_ip_packager.vlnv import Vlnv

pytestmark = pytest.mark.unit


def _resolution(*vlnvs: str) -> Resolution:
    return Resolution(packages=tuple(Vlnv.parse(v) for v in vlnvs))


def test_sha256_digest_is_canonical() -> None:
    assert sha256_digest(b"") == (
        "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_from_resolution_sorts_and_attaches_metadata() -> None:
    resolution = _resolution("acme:lib:b:1.0.0", "acme:lib:a:2.0.0")
    sources = {Vlnv.parse("acme:lib:a:2.0.0"): "path:cores/a"}
    checksums = {Vlnv.parse("acme:lib:a:2.0.0"): "sha256:dead"}
    lock = Lockfile.from_resolution(resolution, sources=sources, checksums=checksums)
    assert [str(p.vlnv) for p in lock.packages] == ["acme:lib:a:2.0.0", "acme:lib:b:1.0.0"]
    assert lock.packages[0].source == "path:cores/a"
    assert lock.packages[1].source == ""  # no metadata -> empty, not an error


def test_to_toml_round_trips() -> None:
    lock = Lockfile(
        packages=(
            LockedPackage(Vlnv.parse("acme:lib:a:2.0.0"), "path:cores/a", "sha256:aa"),
            LockedPackage(Vlnv.parse("acme:lib:b:1.0.0")),
        )
    )
    parsed = Lockfile.from_toml(lock.to_toml())
    assert parsed == lock


def test_opaque_version_round_trips_via_scheme_marker() -> None:
    # A non-SemVer (opaque) version survives serialize/parse via a `scheme` marker.
    lock = Lockfile(packages=(LockedPackage(Vlnv.parse("acme:x:radio:D5020100", "opaque")),))
    toml = lock.to_toml()
    assert 'scheme   = "opaque"' in toml
    parsed = Lockfile.from_toml(toml)
    assert parsed == lock
    assert str(parsed.packages[0].vlnv) == "acme:x:radio:D5020100"


def test_to_toml_is_deterministic_regardless_of_input_order() -> None:
    a = LockedPackage(Vlnv.parse("acme:lib:a:1.0.0"))
    b = LockedPackage(Vlnv.parse("acme:lib:b:1.0.0"))
    assert Lockfile(packages=(a, b)).to_toml() == Lockfile(packages=(b, a)).to_toml()


def test_from_toml_rejects_wrong_version() -> None:
    with pytest.raises(LockfileError, match="version"):
        Lockfile.from_toml("version = 999\n")


def test_from_toml_rejects_bad_vlnv() -> None:
    with pytest.raises(LockfileError, match="vlnv"):
        Lockfile.from_toml(f'version = {LOCKFILE_VERSION}\n[[package]]\nvlnv = "not-a-vlnv"\n')


def test_from_toml_rejects_invalid_toml() -> None:
    with pytest.raises(LockfileError, match="Invalid TOML"):
        Lockfile.from_toml("this is = = not toml")


def test_verify_passes_when_checksums_match() -> None:
    vlnv = Vlnv.parse("acme:lib:a:1.0.0")
    lock = Lockfile(packages=(LockedPackage(vlnv, checksum="sha256:aa"),))
    lock.verify({vlnv: "sha256:aa"})  # no raise


def test_verify_fails_on_mismatch() -> None:
    vlnv = Vlnv.parse("acme:lib:a:1.0.0")
    lock = Lockfile(packages=(LockedPackage(vlnv, checksum="sha256:aa"),))
    with pytest.raises(LockfileError, match="mismatch"):
        lock.verify({vlnv: "sha256:bb"})


def test_verify_fails_when_checksum_missing() -> None:
    vlnv = Vlnv.parse("acme:lib:a:1.0.0")
    lock = Lockfile(packages=(LockedPackage(vlnv, checksum="sha256:aa"),))
    with pytest.raises(LockfileError, match="No checksum"):
        lock.verify({})


def test_verify_skips_unchecksummed_packages() -> None:
    vlnv = Vlnv.parse("acme:lib:a:1.0.0")
    Lockfile(packages=(LockedPackage(vlnv),)).verify({})  # nothing to check -> no raise


def test_matches_resolution() -> None:
    resolution = _resolution("acme:lib:a:1.0.0", "acme:lib:b:1.0.0")
    lock = Lockfile.from_resolution(resolution)
    assert lock.matches_resolution(resolution)
    assert not lock.matches_resolution(_resolution("acme:lib:a:1.0.0"))
