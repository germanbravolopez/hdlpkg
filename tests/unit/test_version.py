"""Unit tests for hdl_ip_packager.version (Version + VersionConstraint).

This is the project's reference test module: a pure unit under test, no fixtures
beyond literals, and dense coverage of the tricky parts (SemVer precedence,
pre-release ordering, and the constraint grammar).
"""

from __future__ import annotations

import itertools

import pytest

from hdl_ip_packager.exceptions import InvalidConstraintError, InvalidVersionError
from hdl_ip_packager.version import (
    OpaqueVersion,
    Version,
    VersionConstraint,
    compatibility_group,
)

pytestmark = pytest.mark.unit


class TestOpaqueVersion:
    @pytest.mark.parametrize("text", ["D5020100", "D4010100", "DB010000", "2024.1", "r3", "1.2"])
    def test_parses_non_semver_tokens(self, text: str) -> None:
        assert str(OpaqueVersion.parse(text)) == text

    @pytest.mark.parametrize("text", ["", "  ", "has space", ":colon", "@bad"])
    def test_rejects_non_tokens(self, text: str) -> None:
        with pytest.raises(InvalidVersionError):
            OpaqueVersion.parse(text)

    def test_lexical_ordering_is_deterministic(self) -> None:
        assert OpaqueVersion.parse("D5020100") < OpaqueVersion.parse("D5020200")
        assert sorted([OpaqueVersion.parse("DB010001"), OpaqueVersion.parse("DB010000")]) == [
            OpaqueVersion.parse("DB010000"),
            OpaqueVersion.parse("DB010001"),
        ]

    def test_not_a_prerelease(self) -> None:
        assert OpaqueVersion.parse("D5020100").is_prerelease is False


class TestCompatibilityGroup:
    def test_major_drives_group_above_one(self) -> None:
        assert compatibility_group(Version.parse("1.4.2")) == ("semver", 1)
        assert compatibility_group(Version.parse("2.0.0")) == ("semver", 2)
        assert compatibility_group(Version.parse("1.0.0")) == compatibility_group(
            Version.parse("1.9.9")
        )

    def test_zero_major_groups_by_minor(self) -> None:
        assert compatibility_group(Version.parse("0.1.0")) == ("semver", 0, 1)
        assert compatibility_group(Version.parse("0.1.5")) == ("semver", 0, 1)
        assert compatibility_group(Version.parse("0.2.0")) != compatibility_group(
            Version.parse("0.1.0")
        )

    def test_zero_zero_groups_by_patch(self) -> None:
        assert compatibility_group(Version.parse("0.0.3")) == ("semver", 0, 0, 3)
        assert compatibility_group(Version.parse("0.0.3")) != compatibility_group(
            Version.parse("0.0.4")
        )

    def test_opaque_scheme_groups_per_version(self) -> None:
        assert compatibility_group(Version.parse("1.0.0"), "opaque") == ("opaque", "1.0.0")
        assert compatibility_group(Version.parse("1.0.0"), "opaque") != compatibility_group(
            Version.parse("1.1.0"), "opaque"
        )


class TestExactConstraint:
    def test_equals_is_exact(self) -> None:
        c = VersionConstraint.parse("=1.2.3")
        assert c.is_exact
        assert c.exact_version == Version.parse("1.2.3")

    def test_caret_and_range_are_not_exact(self) -> None:
        assert not VersionConstraint.parse("^1.2.3").is_exact
        assert not VersionConstraint.parse(">=1.0.0,<2.0.0").is_exact
        assert VersionConstraint.parse("^1.2.3").exact_version is None

    def test_pinned_token_for_semver(self) -> None:
        assert VersionConstraint.parse("=1.2.3").pinned_token == "1.2.3"
        assert VersionConstraint.parse("^1.2.3").pinned_token is None


class TestOpaqueConstraint:
    @pytest.mark.parametrize("text", ["=D5020100", "D5020100", "==2024.1", "2024.1"])
    def test_opaque_exact_pins_parse(self, text: str) -> None:
        c = VersionConstraint.parse(text)
        assert c.opaque is not None
        assert c.is_exact
        assert c.exact_version is None  # not a SemVer Version

    def test_opaque_matches_only_its_exact_token(self) -> None:
        c = VersionConstraint.parse("=D5020100")
        assert c.pinned_token == "D5020100"
        assert c.matches(OpaqueVersion.parse("D5020100"))
        assert not c.matches(OpaqueVersion.parse("D5020200"))

    def test_semver_constraint_never_matches_opaque_version(self) -> None:
        assert not VersionConstraint.parse("^1.0.0").matches(OpaqueVersion.parse("D5020100"))

    def test_semver_pin_is_not_opaque(self) -> None:
        # A SemVer-shaped =pin stays a normal SemVer constraint, not an opaque one.
        assert VersionConstraint.parse("=1.2.3").opaque is None


class TestVersionParsing:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("0.0.0", (0, 0, 0, (), ())),
            ("1.2.3", (1, 2, 3, (), ())),
            ("10.20.30", (10, 20, 30, (), ())),
            ("1.2.3-rc.1", (1, 2, 3, ("rc", "1"), ())),
            ("1.2.3+build.5", (1, 2, 3, (), ("build", "5"))),
            ("1.2.3-alpha.1+exp.sha.5114f85", (1, 2, 3, ("alpha", "1"), ("exp", "sha", "5114f85"))),
            ("  1.2.3  ", (1, 2, 3, (), ())),  # surrounding whitespace tolerated
        ],
    )
    def test_parse_valid(self, text: str, expected: tuple) -> None:
        v = Version.parse(text)
        assert (v.major, v.minor, v.patch, v.prerelease, v.build) == expected

    @pytest.mark.parametrize(
        "text",
        ["1.2", "1.2.3.4", "v1.2.3", "01.2.3", "1.2.3-", "", "abc", "1.2.x"],
    )
    def test_parse_invalid_raises(self, text: str) -> None:
        with pytest.raises(InvalidVersionError):
            Version.parse(text)

    def test_parse_non_string_raises(self) -> None:
        with pytest.raises(InvalidVersionError):
            Version.parse(123)  # type: ignore[arg-type]

    def test_str_roundtrip(self) -> None:
        for text in ("1.2.3", "1.2.3-rc.1", "1.2.3+build.5", "1.2.3-rc.1+build.5"):
            assert str(Version.parse(text)) == text

    def test_is_prerelease_and_core(self) -> None:
        assert Version.parse("1.2.3-rc.1").is_prerelease is True
        assert Version.parse("1.2.3").is_prerelease is False
        assert Version.parse("1.2.3-rc.1+b").core == (1, 2, 3)


class TestVersionOrdering:
    def test_core_ordering(self) -> None:
        order = ["1.0.0", "1.0.1", "1.1.0", "2.0.0"]
        versions = [Version.parse(t) for t in order]
        assert versions == sorted(versions)

    def test_semver_spec_prerelease_ordering(self) -> None:
        # The exact precedence example from semver.org section 11.
        chain = [
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-alpha.beta",
            "1.0.0-beta",
            "1.0.0-beta.2",
            "1.0.0-beta.11",
            "1.0.0-rc.1",
            "1.0.0",
        ]
        versions = [Version.parse(t) for t in chain]
        for lower, higher in itertools.pairwise(versions):
            assert lower < higher, f"{lower} should be < {higher}"
        assert versions == sorted(versions)

    def test_build_metadata_ignored_in_equality(self) -> None:
        assert Version.parse("1.2.3+a") == Version.parse("1.2.3+b")
        assert Version.parse("1.2.3+a") == Version.parse("1.2.3")

    def test_equality_distinguishes_prerelease(self) -> None:
        assert Version.parse("1.2.3-rc.1") != Version.parse("1.2.3")

    def test_hashing_dedups_equal_versions(self) -> None:
        s = {Version.parse("1.2.3+a"), Version.parse("1.2.3+b"), Version.parse("1.2.3")}
        assert len(s) == 1

    def test_comparison_with_non_version_returns_notimplemented(self) -> None:
        assert Version.parse("1.0.0").__eq__("1.0.0") is NotImplemented
        assert Version.parse("1.0.0").__lt__("1.0.0") is NotImplemented


class TestVersionConstraint:
    @pytest.mark.parametrize(
        ("constraint", "version", "expected"),
        [
            # caret (bare == caret)
            ("^1.2.3", "1.2.3", True),
            ("^1.2.3", "1.9.9", True),
            ("^1.2.3", "2.0.0", False),
            ("^1.2.3", "1.2.2", False),
            ("1.2.3", "1.5.0", True),  # bare behaves as caret
            ("^0.2.3", "0.2.9", True),
            ("^0.2.3", "0.3.0", False),
            ("^0.0.3", "0.0.3", True),
            ("^0.0.3", "0.0.4", False),
            # tilde
            ("~1.2.3", "1.2.9", True),
            ("~1.2.3", "1.3.0", False),
            # explicit operators
            ("=1.2.3", "1.2.3", True),
            ("==1.2.3", "1.2.3", True),
            ("=1.2.3", "1.2.4", False),
            (">=1.0.0", "1.0.0", True),
            (">1.0.0", "1.0.0", False),
            ("<=2.0.0", "2.0.0", True),
            ("<2.0.0", "2.0.0", False),
            # AND of clauses
            (">=1.0.0,<2.0.0", "1.5.0", True),
            (">=1.0.0,<2.0.0", "2.0.0", False),
            (">=1.0.0, <2.0.0", "0.9.0", False),  # whitespace tolerated
            # wildcard
            ("*", "9.9.9", True),
            ("", "9.9.9", True),
            ("any", "0.0.1", True),
        ],
    )
    def test_matches(self, constraint: str, version: str, expected: bool) -> None:
        assert VersionConstraint.parse(constraint).matches(Version.parse(version)) is expected

    def test_prerelease_excluded_from_stable_constraints(self) -> None:
        # A caret/wildcard built from stable operands never matches a pre-release.
        assert VersionConstraint.parse("^1.0.0").matches(Version.parse("1.5.0-rc.1")) is False
        assert VersionConstraint.parse("*").matches(Version.parse("1.0.0-alpha")) is False
        assert VersionConstraint.parse("^1.0.0").matches(Version.parse("2.0.0-alpha")) is False

    def test_prerelease_allowed_when_operand_is_prerelease(self) -> None:
        c = VersionConstraint.parse(">=1.5.0-rc.1,<1.6.0")
        assert c.matches(Version.parse("1.5.0-rc.1")) is True
        assert c.matches(Version.parse("1.5.0-rc.2")) is True
        assert c.matches(Version.parse("1.5.0")) is True
        # but a pre-release of a *different* base is still excluded
        assert c.matches(Version.parse("1.5.9-rc.1")) is False

    @pytest.mark.parametrize(
        "constraint",
        [">=", "^", ">=abc", "1.0.0,,", ">=1.0.0,", "~not.a.version"],
    )
    def test_invalid_constraints_raise(self, constraint: str) -> None:
        with pytest.raises(InvalidConstraintError):
            VersionConstraint.parse(constraint)

    def test_non_string_constraint_raises(self) -> None:
        with pytest.raises(InvalidConstraintError):
            VersionConstraint.parse(1.0)  # type: ignore[arg-type]

    def test_str_preserves_raw(self) -> None:
        assert str(VersionConstraint.parse(">=1.0.0,<2.0.0")) == ">=1.0.0,<2.0.0"
        assert str(VersionConstraint.parse("")) == "*"
