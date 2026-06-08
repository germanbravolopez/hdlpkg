"""Unit tests for hdl_ip_packager.vlnv (PackageRef + Vlnv)."""

from __future__ import annotations

import pytest

from hdl_ip_packager.exceptions import InvalidVlnvError
from hdl_ip_packager.version import OpaqueVersion, Version
from hdl_ip_packager.vlnv import PackageRef, Vlnv

pytestmark = pytest.mark.unit


class TestOpaqueVlnv:
    def test_parse_opaque_scheme_accepts_non_semver(self) -> None:
        v = Vlnv.parse("acme:x:radio:D5020100", scheme="opaque")
        assert isinstance(v.version, OpaqueVersion)
        assert str(v) == "acme:x:radio:D5020100"

    def test_default_scheme_still_rejects_non_semver(self) -> None:
        with pytest.raises(InvalidVlnvError):
            Vlnv.parse("acme:x:radio:D5020100")

    def test_with_version_accepts_opaque_instance(self) -> None:
        v = PackageRef.parse("acme:x:radio").with_version(OpaqueVersion.parse("D5020100"))
        assert str(v) == "acme:x:radio:D5020100"


class TestVlnv:
    def test_parse_and_str_roundtrip(self) -> None:
        v = Vlnv.parse("acme:comm:uart:1.2.0")
        assert v.vendor == "acme"
        assert v.library == "comm"
        assert v.name == "uart"
        assert v.version == Version.parse("1.2.0")
        assert str(v) == "acme:comm:uart:1.2.0"

    def test_parse_with_prerelease_version(self) -> None:
        v = Vlnv.parse("acme:comm:uart:2.0.0-rc.1")
        assert v.version.is_prerelease
        assert str(v) == "acme:comm:uart:2.0.0-rc.1"

    @pytest.mark.parametrize(
        "text",
        [
            "acme:comm:uart",  # too few parts
            "acme:comm:uart:1:2",  # too many parts
            "acme:comm:uart:1.2",  # bad version
            "acme::uart:1.0.0",  # empty library segment
            "acme:comm:ua rt:1.0.0",  # space in name
            "_acme:comm:uart:1.0.0",  # segment cannot start with underscore
        ],
    )
    def test_parse_invalid_raises(self, text: str) -> None:
        with pytest.raises(InvalidVlnvError):
            Vlnv.parse(text)

    def test_parse_non_string_raises(self) -> None:
        with pytest.raises(InvalidVlnvError):
            Vlnv.parse(42)  # type: ignore[arg-type]

    def test_ref_property(self) -> None:
        v = Vlnv.parse("acme:comm:uart:1.2.0")
        assert v.ref == PackageRef("acme", "comm", "uart")

    def test_equality_and_hashing(self) -> None:
        a = Vlnv.parse("acme:comm:uart:1.2.0")
        b = Vlnv.parse("acme:comm:uart:1.2.0")
        c = Vlnv.parse("acme:comm:uart:1.2.1")
        assert a == b
        assert a != c
        assert len({a, b, c}) == 2

    def test_construct_with_non_version_raises(self) -> None:
        with pytest.raises(InvalidVlnvError):
            Vlnv("acme", "comm", "uart", "1.2.0")  # type: ignore[arg-type]


class TestPackageRef:
    def test_parse_and_str(self) -> None:
        ref = PackageRef.parse("acme:comm:uart")
        assert (ref.vendor, ref.library, ref.name) == ("acme", "comm", "uart")
        assert str(ref) == "acme:comm:uart"

    @pytest.mark.parametrize("text", ["acme:comm", "acme:comm:uart:1.0.0", "acme:comm:"])
    def test_parse_invalid_raises(self, text: str) -> None:
        with pytest.raises(InvalidVlnvError):
            PackageRef.parse(text)

    def test_with_version_from_string(self) -> None:
        v = PackageRef.parse("acme:comm:uart").with_version("1.2.0")
        assert isinstance(v, Vlnv)
        assert str(v) == "acme:comm:uart:1.2.0"

    def test_with_version_from_version_object(self) -> None:
        v = PackageRef.parse("acme:comm:uart").with_version(Version.parse("3.1.4"))
        assert str(v) == "acme:comm:uart:3.1.4"

    def test_with_version_invalid_raises(self) -> None:
        with pytest.raises(InvalidVlnvError):
            PackageRef.parse("acme:comm:uart").with_version("not-a-version")
