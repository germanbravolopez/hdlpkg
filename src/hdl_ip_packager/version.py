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
from typing import Literal

from .exceptions import InvalidConstraintError, InvalidVersionError

__all__ = [
    "DEFAULT_VERSION_SCHEME",
    "SUPPORTED_VERSION_SCHEMES",
    "AnyVersion",
    "CalVer",
    "MonotonicVersion",
    "OpaqueVersion",
    "Version",
    "VersionConstraint",
    "VersionScheme",
    "compatibility_group",
    "parse_version",
]

# How a package's versions are interpreted for *compatibility* (see the resolver):
#
# * ``"semver"`` (default) -- full SemVer 2.0.0 precedence and caret/tilde ranges;
#   dependents on the same major unify to the newest satisfying version.
# * ``"calver"`` -- ordered numeric date/calendar versions (``2024.1``, ``2024.10``,
#   ``2025.2.3``). Ordered component-wise; the **first component (the year) is the
#   compatibility boundary**, so ``^2024.1`` == ``>=2024.1, <2025`` and same-year
#   dependents unify (year-as-major).
# * ``"monotonic"`` -- a single ordered revision (``r3``, ``rev12``, ``12``). All
#   revisions are one compatibility group (newer supersedes), so ``^r3`` == ``>=r3``
#   selects the newest; ``~r3`` / ``=r3`` pin exactly.
# * ``"opaque"`` -- versions are unordered tokens with no compatibility relation:
#   dependents must pin an exact version and every distinct pin is its own group.
#
# For the non-SemVer schemes a **bare** constraint (no operator) means an *exact*
# pin (those schemes lack SemVer's caret default); use ``^`` / ``~`` / ranges
# explicitly for flexibility.
VersionScheme = Literal["semver", "calver", "monotonic", "opaque"]
SUPPORTED_VERSION_SCHEMES: tuple[VersionScheme, ...] = (
    "semver",
    "calver",
    "monotonic",
    "opaque",
)
DEFAULT_VERSION_SCHEME: VersionScheme = "semver"


def parse_version(text: str, scheme: VersionScheme = "semver") -> AnyVersion:
    """Parse *text* into the version type for *scheme*, raising :class:`InvalidVersionError`.

    ``semver`` -> :class:`Version`, ``calver`` -> :class:`CalVer`,
    ``monotonic`` -> :class:`MonotonicVersion`, ``opaque`` -> :class:`OpaqueVersion`.
    """
    if scheme == "opaque":
        return OpaqueVersion.parse(text)
    if scheme == "calver":
        return CalVer.parse(text)
    if scheme == "monotonic":
        return MonotonicVersion.parse(text)
    return Version.parse(text)


def compatibility_group(
    version: AnyVersion, scheme: VersionScheme = "semver"
) -> tuple[object, ...]:
    """Return the *compatibility group* key of *version* under *scheme*.

    Two versions are in the same group iff a dependent on one may transparently be
    satisfied by the other (so the resolver unifies them). Versions in *different*
    groups are mutually incompatible and may coexist (subject to the conflict
    policy). The key is hashable and only meaningful per package.

    SemVer (Cargo semantics): the major for ``major >= 1``; for ``0.y.z`` the minor
    (``^0.y`` allows patch changes only), and for ``0.0.z`` the patch. CalVer: the
    first component (the year), so same-year versions unify. Monotonic: a single
    shared group (all revisions are compatible). Opaque: the version itself, so every
    distinct version is its own group.
    """
    if isinstance(version, OpaqueVersion) or scheme == "opaque":
        return ("opaque", str(version))
    if isinstance(version, MonotonicVersion) or scheme == "monotonic":
        return ("monotonic",)
    if isinstance(version, CalVer):
        return ("calver", version.components[0])
    if version.major > 0:
        return ("semver", version.major)
    if version.minor > 0:
        return ("semver", 0, version.minor)
    return ("semver", 0, 0, version.patch)


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
            raise InvalidVersionError(
                f"Not a valid semantic version: {text!r}. If this is a vendor or date "
                "version code, set [package].scheme (or 'hdlpkg init --scheme') to "
                "'opaque', 'monotonic', or 'calver'."
            )
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


# An opaque version token: a non-SemVer identifier (calver ``2024.1``, a vendor tag
# ``D5020100``, a monotonic ``r3``). Same character set as a VLNV segment, plus ``+``.
_OPAQUE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$")


@total_ordering
@dataclass(frozen=True)
class OpaqueVersion:
    """A version with no SemVer compatibility relation, used by ``scheme = "opaque"``.

    The packager carries the token but does **not** interpret it: there is no
    precedence beyond a deterministic lexical order (for stable output), no ranges,
    and no newest-compatible selection. Dependents must pin an exact ``=`` version.
    """

    raw: str

    @classmethod
    def parse(cls, text: str) -> OpaqueVersion:
        """Parse an opaque version token, raising :class:`InvalidVersionError` on failure."""
        if not isinstance(text, str) or not _OPAQUE_VERSION_RE.match(text.strip()):
            raise InvalidVersionError(f"Not a valid opaque version token: {text!r}")
        return cls(text.strip())

    @property
    def is_prerelease(self) -> bool:
        """Always False -- an opaque token has no pre-release concept."""
        return False

    def __str__(self) -> str:
        return self.raw

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, OpaqueVersion):
            return NotImplemented
        return self.raw < other.raw  # lexical: deterministic, not semantic


# A calendar/numeric version token (``scheme = "calver"``): one or more dot-separated
# non-negative integers, e.g. ``2024.1`` or ``2024.10.3``.
_CALVER_RE = re.compile(r"^\d+(?:\.\d+)*$")

# A monotonic revision (``scheme = "monotonic"``): an optional letter prefix then an
# integer, e.g. ``r3``, ``rev12``, ``12``.
_MONOTONIC_RE = re.compile(r"^(?P<prefix>[A-Za-z]*)(?P<rev>\d+)$")


@total_ordering
@dataclass(frozen=True)
class CalVer:
    """An ordered calendar/numeric version, used by ``scheme = "calver"``.

    A tuple of non-negative integer ``components`` (``2024.1`` -> ``(2024, 1)``),
    compared component-wise (shorter padded with zeros, then the raw string breaks a
    value tie for a deterministic total order). The **first component is the
    compatibility boundary** (year-as-major): ``^2024.1`` allows ``<2025`` only.
    """

    components: tuple[int, ...]
    raw: str

    @classmethod
    def parse(cls, text: str) -> CalVer:
        """Parse a CalVer token, raising :class:`InvalidVersionError` on failure."""
        if not isinstance(text, str) or not _CALVER_RE.match(text.strip()):
            raise InvalidVersionError(f"Not a valid calver version: {text!r}")
        stripped = text.strip()
        return cls(tuple(int(part) for part in stripped.split(".")), stripped)

    @property
    def is_prerelease(self) -> bool:
        return False

    def __str__(self) -> str:
        return self.raw

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, CalVer):
            return NotImplemented
        width = max(len(self.components), len(other.components))
        a = self.components + (0,) * (width - len(self.components))
        b = other.components + (0,) * (width - len(other.components))
        if a != b:
            return a < b
        return self.raw < other.raw  # equal value -> stable tiebreak on the literal


@total_ordering
@dataclass(frozen=True)
class MonotonicVersion:
    """An ordered monotonic revision, used by ``scheme = "monotonic"``.

    A single integer ``revision`` with an optional letter prefix (``r3`` -> prefix
    ``r``, revision ``3``); ordered by the integer. All revisions share one
    compatibility group (a newer revision supersedes an older one).
    """

    revision: int
    raw: str

    @classmethod
    def parse(cls, text: str) -> MonotonicVersion:
        """Parse a monotonic revision, raising :class:`InvalidVersionError` on failure."""
        match = _MONOTONIC_RE.match(text.strip()) if isinstance(text, str) else None
        if match is None:
            raise InvalidVersionError(f"Not a valid monotonic version: {text!r}")
        return cls(int(match.group("rev")), text.strip())

    @property
    def is_prerelease(self) -> bool:
        return False

    def __str__(self) -> str:
        return self.raw

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, MonotonicVersion):
            return NotImplemented
        if self.revision != other.revision:
            return self.revision < other.revision
        return self.raw < other.raw


# Any kind of version a core may declare, depending on its ``[package].scheme``.
AnyVersion = Version | OpaqueVersion | CalVer | MonotonicVersion


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


def _is_semver(text: str) -> bool:
    """True if *text* parses as a SemVer version."""
    try:
        Version.parse(text)
    except InvalidVersionError:
        return False
    return True


def _is_ordered_operand(text: str) -> bool:
    """True if *text* is a calver- or monotonic-shaped (non-SemVer) version token."""
    return bool(_CALVER_RE.match(text) or _MONOTONIC_RE.match(text))


def _calver_caret_upper(v: CalVer) -> CalVer:
    """Exclusive upper bound for ``^v`` on calver: the next *first component* (year)."""
    nxt = v.components[0] + 1
    return CalVer((nxt,), str(nxt))


def _calver_tilde_upper(v: CalVer) -> CalVer:
    """Exclusive upper bound for ``~v`` on calver: bump the last declared component."""
    comps = (*v.components[:-1], v.components[-1] + 1)
    return CalVer(comps, ".".join(str(c) for c in comps))


def _calver_clause_matches(op: str, operand_text: str, candidate: CalVer) -> bool:
    """Test one ordered clause against a CalVer candidate (bare/`^` = year-range)."""
    try:
        operand = CalVer.parse(operand_text)
    except InvalidVersionError:
        return False
    if op in ("", "^"):
        return operand <= candidate < _calver_caret_upper(operand)
    if op == "~":
        return operand <= candidate < _calver_tilde_upper(operand)
    if op in ("=", "=="):
        return candidate == operand
    if op == ">":
        return candidate > operand
    if op == ">=":
        return candidate >= operand
    if op == "<":
        return candidate < operand
    return candidate <= operand  # op == "<="


def _monotonic_clause_matches(op: str, operand_text: str, candidate: MonotonicVersion) -> bool:
    """Test one ordered clause against a monotonic candidate (bare/`^` = at-least)."""
    try:
        operand = MonotonicVersion.parse(operand_text)
    except InvalidVersionError:
        return False
    if op in ("", "^", ">="):
        return candidate >= operand
    if op in ("~", "=", "=="):
        return candidate == operand
    if op == ">":
        return candidate > operand
    if op == "<":
        return candidate < operand
    return candidate <= operand  # op == "<="


def _opaque_exact_token(raw: str) -> str | None:
    """Return the opaque exact-pin token in *raw*, or None if it is not one.

    An opaque pin is a single clause (no commas) that is a bare token or ``=``/``==``
    followed by a token, where the token is a valid opaque identifier but **not** a
    SemVer version (so a real SemVer bare/``=`` constraint takes the normal path).
    """
    if "," in raw:
        return None
    token = raw
    for prefix in ("==", "="):
        if token.startswith(prefix):
            token = token[len(prefix) :].strip()
            break
    if not _OPAQUE_VERSION_RE.match(token):
        return None
    try:
        Version.parse(token)
    except InvalidVersionError:
        return token
    return None  # it parsed as SemVer -> not opaque


@dataclass(frozen=True)
class VersionConstraint:
    """A parsed version constraint that a :class:`Version` may or may not satisfy.

    Construct via :meth:`parse`. The constraint is an *AND* of one or more
    comparators; ``*`` / ``any`` / the empty string means "any stable version".
    """

    comparators: tuple[_Comparator, ...]
    raw: str
    matches_any: bool = False
    opaque: str | None = None  # an exact pin on a non-SemVer (opaque) version token
    # Deferred (op, operand) clauses for an ordered non-SemVer scheme (calver /
    # monotonic). Interpreted at match time against the candidate's type, because the
    # dependency's scheme is not known when the constraint string is parsed.
    ordered: tuple[tuple[str, str], ...] | None = None

    @classmethod
    def parse(cls, text: str) -> VersionConstraint:
        """Parse a constraint string, raising :class:`InvalidConstraintError` on failure."""
        if not isinstance(text, str):
            raise InvalidConstraintError(f"Constraint must be a string, got {type(text).__name__}")
        raw = text.strip()
        if raw in ("", "*", "any"):
            return cls(comparators=(), raw=raw or "*", matches_any=True)

        opaque = _opaque_exact_token(raw)
        if opaque is not None:
            # A bare or ``=`` pin whose operand is not SemVer (e.g. ``=D5020100``,
            # ``2024.1``, ``r3``): an exact pin. For non-SemVer schemes a bare
            # constraint means *exact* (those schemes lack a caret default).
            return cls(comparators=(), raw=raw, opaque=opaque)

        clauses = cls._split_clauses(raw, text)
        if all(_is_semver(operand) for _op, operand in clauses):
            comparators: list[_Comparator] = []
            for op, operand in clauses:
                comparators.extend(cls._expand_semver(op, operand))
            return cls(comparators=tuple(comparators), raw=raw)
        if all(_is_ordered_operand(operand) for _op, operand in clauses):
            # An explicit-operator constraint over calver/monotonic operands; the
            # scheme decides how each clause is interpreted at match time.
            return cls(comparators=(), raw=raw, ordered=tuple(clauses))
        raise InvalidConstraintError(
            f"Invalid constraint {text!r}: operands are not SemVer, calver, or monotonic versions"
        )

    @staticmethod
    def _split_clauses(raw: str, full: str) -> list[tuple[str, str]]:
        """Split a constraint into ``(op, operand)`` clauses; bare operand -> op ``""``."""
        clauses: list[tuple[str, str]] = []
        for token in raw.split(","):
            clause = token.strip()
            if not clause:
                raise InvalidConstraintError(f"Empty clause in constraint {full!r}")
            m = _OP_RE.match(clause)
            if m:
                op, rest = m.group(1), m.group(2).strip()
            else:
                op, rest = "", clause  # bare
            if not rest:
                raise InvalidConstraintError(f"Missing version after {op!r} in {full!r}")
            clauses.append((op, rest))
        return clauses

    @staticmethod
    def _expand_semver(op: str, rest: str) -> list[_Comparator]:
        version = Version.parse(rest)  # caller guarantees this parses
        if op in ("^", ""):  # bare => caret (Cargo/npm convention)
            return [_Comparator(">=", version), _Comparator("<", _caret_upper(version))]
        if op == "~":
            return [_Comparator(">=", version), _Comparator("<", _tilde_upper(version))]
        if op == "==":
            op = "="
        return [_Comparator(op, version)]

    @property
    def is_exact(self) -> bool:
        """True if this constraint pins a single exact version (``=X.Y.Z`` or opaque)."""
        if self.opaque is not None:
            return True
        return len(self.comparators) == 1 and self.comparators[0].op == "="

    @property
    def exact_version(self) -> Version | None:
        """The pinned :class:`Version` if this is an exact SemVer constraint, else ``None``."""
        if self.opaque is not None:
            return None
        return self.comparators[0].version if self.is_exact else None

    @property
    def pinned_token(self) -> str | None:
        """The exact-pinned version string (SemVer or opaque), or ``None`` if not exact."""
        if self.opaque is not None:
            return self.opaque
        exact = self.exact_version
        return str(exact) if exact is not None else None

    def _prerelease_allowed(self, candidate: Version) -> bool:
        """A pre-release candidate is only allowed if a comparator targets its base triple."""
        return any(
            c.version.is_prerelease and c.version.core == candidate.core for c in self.comparators
        )

    def matches(self, candidate: AnyVersion) -> bool:
        """Return True if *candidate* satisfies this constraint."""
        if self.opaque is not None:
            return str(candidate) == self.opaque
        if self.ordered is not None:
            return self._matches_ordered(candidate)
        # A SemVer comparator (or ``*``) path: only SemVer versions can satisfy it,
        # except ``*`` which admits any stable version of any scheme.
        if not isinstance(candidate, Version):
            return self.matches_any
        if candidate.is_prerelease and not self._prerelease_allowed(candidate):
            return False
        if self.matches_any:
            return True
        return all(c.matches(candidate) for c in self.comparators)

    def _matches_ordered(self, candidate: AnyVersion) -> bool:
        """Interpret the deferred ordered clauses against *candidate*'s scheme."""
        clauses = self.ordered or ()
        if isinstance(candidate, CalVer):
            return all(_calver_clause_matches(op, operand, candidate) for op, operand in clauses)
        if isinstance(candidate, MonotonicVersion):
            return all(_monotonic_clause_matches(op, operand, candidate) for op, operand in clauses)
        return False  # an ordered non-SemVer constraint vs a SemVer/opaque candidate

    def __str__(self) -> str:
        return self.raw
