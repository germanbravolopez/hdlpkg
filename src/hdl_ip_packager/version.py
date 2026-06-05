"""Semantic versioning: parsing, precedence, and constraint matching.

This is a self-contained, pure module (no I/O, no global state). It implements
the subset of `Semantic Versioning 2.0.0 <https://semver.org>`_ that an IP
packager needs:

* :class:`Version` — parse ``MAJOR.MINOR.PATCH[-prerelease][+build]`` and compare
  two versions with the full SemVer precedence rules.
* :class:`VersionConstraint` — parse a small constraint grammar (``=``, ``>``,
  ``>=``, ``<``, ``<=``, ``^``, ``~``, ``*``, and comma-separated *AND*) and test
  whether a :class:`Version` satisfies it.

Design notes worth knowing before you change anything:

* Build metadata (``+sha.1``) is ignored for precedence, per SemVer §10.
* A bare constraint (``1.2.3`` with no operator) means **caret** (``^1.2.3``).
  This matches the dominant library-ecosystem convention (Cargo, npm) that we
  adopt project-wide. See ``docs/research/state_of_the_art.md``.
* Pre-release handling: a comparator built from a *stable* operand does **not**
  match pre-release versions. A pre-release version (e.g. ``1.4.0-rc.1``) only
  satisfies a constraint if some comparator's operand is itself a pre-release of
  the *same* ``MAJOR.MINOR.PATCH``. This is the Cargo rule and keeps ``^1.0.0``
  from silently pulling in ``2.0.0-alpha``.

Because it is pure and fully unit-tested, this module is the reference example
for the project's "implement for testability" rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

from .exceptions import InvalidConstraintError, InvalidVersionError

__all__ = ["Version", "VersionConstraint"]

# Official SemVer 2.0.0 regex (anchored), adapted with named groups.
_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def _prerelease_lt(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Return True if pre-release tuple *a* has lower precedence than *b* (SemVer §11)."""
    if a == b:
        return False
    # A normal version (no pre-release) has HIGHER precedence than a pre-release.
    if not a:
        return False
    if not b:
        return True
    for x, y in zip(a, b, strict=False):
        if x == y:
            continue
        x_num, y_num = x.isdigit(), y.isdigit()
        if x_num and y_num:
            return int(x) < int(y)
        if x_num != y_num:
            # Numeric identifiers always have lower precedence than alphanumeric.
            return x_num
        return x < y  # both alphanumeric: ASCII order
    # All shared identifiers equal -> the one with fewer fields is lower.
    return len(a) < len(b)


@total_ordering
@dataclass(frozen=True)
class Version:
    """A parsed, comparable semantic version.

    Instances are immutable and hashable. Equality and ordering follow SemVer
    precedence (build metadata ignored), so versions sort correctly in lists,
    ``min``/``max``, and ``sorted``.
    """

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> Version:
        """Parse a version string, raising :class:`InvalidVersionError` on failure."""
        if not isinstance(text, str):
            raise InvalidVersionError(f"Version must be a string, got {type(text).__name__}")
        m = _SEMVER_RE.match(text.strip())
        if not m:
            raise InvalidVersionError(f"Not a valid semantic version: {text!r}")
        pre = tuple(m.group("prerelease").split(".")) if m.group("prerelease") else ()
        build = tuple(m.group("build").split(".")) if m.group("build") else ()
        return cls(
            int(m.group("major")),
            int(m.group("minor")),
            int(m.group("patch")),
            pre,
            build,
        )

    @property
    def is_prerelease(self) -> bool:
        """True if this version carries a pre-release tag (e.g. ``-rc.1``)."""
        return bool(self.prerelease)

    @property
    def core(self) -> tuple[int, int, int]:
        """The ``(major, minor, patch)`` triple, ignoring pre-release/build."""
        return (self.major, self.minor, self.patch)

    def __str__(self) -> str:
        out = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            out += "-" + ".".join(self.prerelease)
        if self.build:
            out += "+" + ".".join(self.build)
        return out

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self.core == other.core and self.prerelease == other.prerelease

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        if self.core != other.core:
            return self.core < other.core
        return _prerelease_lt(self.prerelease, other.prerelease)

    def __hash__(self) -> int:
        return hash((self.core, self.prerelease))


@dataclass(frozen=True)
class _Comparator:
    """A single primitive comparison: ``op`` in {=, >, >=, <, <=} against ``version``."""

    op: str
    version: Version

    def matches(self, candidate: Version) -> bool:
        if self.op == "=":
            return candidate == self.version
        if self.op == ">":
            return candidate > self.version
        if self.op == ">=":
            return candidate >= self.version
        if self.op == "<":
            return candidate < self.version
        if self.op == "<=":
            return candidate <= self.version
        raise AssertionError(f"unknown operator {self.op!r}")  # pragma: no cover


# Operator prefixes recognised in a constraint clause, longest first so that
# ">=" is matched before ">".
_OP_RE = re.compile(r"^(>=|<=|==|=|>|<|\^|~)\s*(.*)$")


def _caret_upper(v: Version) -> Version:
    """Exclusive upper bound for ``^v`` (compatible-release)."""
    if v.major > 0:
        return Version(v.major + 1, 0, 0)
    if v.minor > 0:
        return Version(0, v.minor + 1, 0)
    return Version(0, 0, v.patch + 1)


def _tilde_upper(v: Version) -> Version:
    """Exclusive upper bound for ``~v`` (allow patch-level changes)."""
    return Version(v.major, v.minor + 1, 0)


@dataclass(frozen=True)
class VersionConstraint:
    """A parsed version constraint that a :class:`Version` may or may not satisfy.

    Construct via :meth:`parse`. The constraint is an *AND* of one or more
    comparators; ``*`` / ``any`` / the empty string means "any stable version".
    """

    comparators: tuple[_Comparator, ...]
    raw: str
    matches_any: bool = False

    @classmethod
    def parse(cls, text: str) -> VersionConstraint:
        """Parse a constraint string, raising :class:`InvalidConstraintError` on failure."""
        if not isinstance(text, str):
            raise InvalidConstraintError(f"Constraint must be a string, got {type(text).__name__}")
        raw = text.strip()
        if raw in ("", "*", "any"):
            return cls(comparators=(), raw=raw or "*", matches_any=True)

        comparators: list[_Comparator] = []
        for token in raw.split(","):
            clause = token.strip()
            if not clause:
                raise InvalidConstraintError(f"Empty clause in constraint {text!r}")
            comparators.extend(cls._parse_clause(clause, text))
        return cls(comparators=tuple(comparators), raw=raw)

    @staticmethod
    def _parse_clause(clause: str, full: str) -> list[_Comparator]:
        m = _OP_RE.match(clause)
        if m:
            op, rest = m.group(1), m.group(2).strip()
        else:
            op, rest = "^", clause  # bare version => caret (Cargo/npm convention)
        if not rest:
            raise InvalidConstraintError(f"Missing version after {op!r} in {full!r}")
        try:
            version = Version.parse(rest)
        except InvalidVersionError as exc:
            raise InvalidConstraintError(f"In constraint {full!r}: {exc}") from exc

        if op == "==":
            op = "="
        if op == "^":
            return [_Comparator(">=", version), _Comparator("<", _caret_upper(version))]
        if op == "~":
            return [_Comparator(">=", version), _Comparator("<", _tilde_upper(version))]
        return [_Comparator(op, version)]

    def _prerelease_allowed(self, candidate: Version) -> bool:
        """A pre-release candidate is only allowed if a comparator targets its base triple."""
        return any(
            c.version.is_prerelease and c.version.core == candidate.core for c in self.comparators
        )

    def matches(self, candidate: Version) -> bool:
        """Return True if *candidate* satisfies this constraint."""
        if candidate.is_prerelease and not self._prerelease_allowed(candidate):
            return False
        if self.matches_any:
            return True
        return all(c.matches(candidate) for c in self.comparators)

    def __str__(self) -> str:
        return self.raw
