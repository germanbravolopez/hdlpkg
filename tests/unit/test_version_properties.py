"""Property-based tests for ``version.py`` using Hypothesis.

The example-based suite in ``test_version.py`` pins down specific cases; this
module asserts the *invariants* that must hold for every input -- the kind of
universal claim Hypothesis is built to falsify:

* ``Version.parse(str(v)) == v`` and the string round-trips exactly.
* Ordering is a total order (trichotomy + antisymmetry) and ``sorted`` agrees.
* A constraint built from a version contains/excludes that version as its
  operator dictates.
* ``Version.parse`` / ``VersionConstraint.parse`` only ever raise their declared
  error type -- arbitrary text never leaks an unexpected exception.
"""

from __future__ import annotations

import contextlib
import string
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hdlpkg.exceptions import InvalidConstraintError, InvalidVersionError
from hdlpkg.version import Version, VersionConstraint

pytestmark = pytest.mark.unit

# Keep the property loop snappy for the local fast suite, and disable the
# per-example deadline: this project's CI/dev machines include AV-throttled paths
# (see CLAUDE.md) that make wall-clock-per-example checks flaky, not informative.
prop_settings = settings(max_examples=60, deadline=None)

# Identifiers that are valid for both pre-release and build metadata. Numeric
# identifiers come from ints (so never carry a leading zero); alphabetic ones
# always contain a non-digit, so they take the alphanumeric grammar branch.
_numeric_ident = st.integers(min_value=0, max_value=99).map(str)
_alpha_ident = st.text(alphabet=string.ascii_letters + "-", min_size=1, max_size=4)
_ident = st.one_of(_numeric_ident, _alpha_ident)


@st.composite
def _versions(draw: st.DrawFn, *, prerelease: bool = True, build: bool = True) -> Version:
    major = draw(st.integers(min_value=0, max_value=40))
    minor = draw(st.integers(min_value=0, max_value=40))
    patch = draw(st.integers(min_value=0, max_value=40))
    pre = tuple(draw(st.lists(_ident, max_size=3))) if prerelease else ()
    bld = tuple(draw(st.lists(_ident, max_size=2))) if build else ()
    return Version(major, minor, patch, pre, bld)


def versions(*, prerelease: bool = True, build: bool = True) -> st.SearchStrategy[Version]:
    """Strategy producing valid :class:`Version` instances."""
    return _versions(prerelease=prerelease, build=build)


@prop_settings
@given(versions())
def test_parse_str_round_trips(v: Version) -> None:
    parsed = Version.parse(str(v))
    assert parsed == v
    # Build metadata is dropped from equality but preserved in the rendering.
    assert str(parsed) == str(v)


@prop_settings
@given(versions(), versions())
def test_ordering_is_trichotomous(a: Version, b: Version) -> None:
    assert sum((a < b, a == b, a > b)) == 1


@prop_settings
@given(versions(), versions())
def test_ordering_is_antisymmetric(a: Version, b: Version) -> None:
    if a < b:
        assert b > a
        assert not (b < a)


@prop_settings
@given(st.lists(versions(), max_size=8))
def test_sorted_is_nondecreasing(vs: list[Version]) -> None:
    ordered = sorted(vs)
    assert all(x <= y for x, y in pairwise(ordered))


@prop_settings
@given(versions(prerelease=False))
def test_constraint_contains_its_own_version(v: Version) -> None:
    # Bare version == caret, plus the explicit comparators that should include v.
    for text in (str(v), f"={v}", f">={v}", f"<={v}", f"^{v}", f"~{v}"):
        assert VersionConstraint.parse(text).matches(v), text
    # Strict comparators against v exclude v itself.
    assert not VersionConstraint.parse(f">{v}").matches(v)
    assert not VersionConstraint.parse(f"<{v}").matches(v)


@prop_settings
@given(versions(prerelease=False, build=False))
def test_caret_excludes_next_major(v: Version) -> None:
    if v.major > 0:
        assert not VersionConstraint.parse(f"^{v}").matches(Version(v.major + 1, 0, 0))


@prop_settings
@given(st.text())
def test_version_parse_raises_only_invalid_version(text: str) -> None:
    with contextlib.suppress(InvalidVersionError):
        Version.parse(text)


@prop_settings
@given(st.text())
def test_constraint_parse_raises_only_invalid_constraint(text: str) -> None:
    with contextlib.suppress(InvalidConstraintError):
        VersionConstraint.parse(text)
