# Versioning — `version.py`

Semantic-version parsing, precedence, and constraint matching. Pure module (no I/O),
the reference example for the project's testability rule.

- **Source**: [src/hdl_ip_packager/version.py](../../src/hdl_ip_packager/version.py)
- **Import**: `from hdl_ip_packager import Version, VersionConstraint, OpaqueVersion, compatibility_group`

## Purpose

Every IP core is identified partly by a [SemVer 2.0.0](https://semver.org) version,
and dependencies are expressed as *constraints* over versions. This module is the
single place that knows how to parse versions, order them, and decide whether a
version satisfies a constraint.

## `Version`

A parsed, immutable, hashable, totally-ordered semantic version.

| Member | Description |
|--------|-------------|
| `Version.parse(text) -> Version` | Parse `MAJOR.MINOR.PATCH[-prerelease][+build]`. Raises `InvalidVersionError`. |
| `major`, `minor`, `patch` | The numeric core (ints). |
| `prerelease`, `build` | Dot-split identifier tuples (e.g. `("rc", "1")`). |
| `is_prerelease` | `True` if a pre-release tag is present. |
| `core` | The `(major, minor, patch)` triple. |
| `str(v)` | Round-trips: `Version.parse(str(v)) == v`. |

**Ordering** follows SemVer precedence (§11): the core triple compares first, then
pre-release identifiers (numeric < alphanumeric, fewer fields < more); a normal
version outranks any pre-release of the same core. **Build metadata is ignored** for
both equality and ordering (§10), so `1.0.0+a == 1.0.0+b`. Because ordering is a
genuine total order, `sorted()`, `min()`, and `max()` all work on versions.

## `VersionConstraint`

A parsed constraint that a `Version` may or may not satisfy. Build via
`VersionConstraint.parse(text)` (raises `InvalidConstraintError`).

| Grammar | Meaning |
|---------|---------|
| `=1.2.3` / `==1.2.3` | exactly `1.2.3` |
| `>1.2.3`, `>=1.2.3`, `<2.0.0`, `<=1.9.9` | inequality bounds |
| `^1.2.3` | compatible release: `>=1.2.3, <2.0.0` (for `0.x`: `^0.2.3` = `>=0.2.3, <0.3.0`) |
| `~1.2.3` | patch-level: `>=1.2.3, <1.3.0` |
| `1.2.3` (bare, no operator) | **caret** — same as `^1.2.3` (Cargo/npm convention) |
| `a, b` (comma) | logical AND of clauses (e.g. `>=1.2.0,<2.0.0`) |
| `*`, `any`, or empty | any stable version |

`constraint.matches(version) -> bool` tests satisfaction. `str(constraint)` returns
the original text. `constraint.is_exact` / `exact_version` / `pinned_token` expose a
single `=` pin (SemVer or opaque) for the resolver.

**Pre-release rule** (the Cargo rule): a constraint built from a *stable* operand
never matches a pre-release version, so `^1.0.0` will **not** pull in `2.0.0-alpha`
or even `1.5.0-rc.1`. A pre-release candidate is allowed only when some clause's
operand is itself a pre-release of the *same* `MAJOR.MINOR.PATCH` (e.g. `>=1.4.0-rc.1`
admits `1.4.0-rc.2`).

## Compatibility groups — `compatibility_group(version, scheme)`

The resolver groups a package's versions into *compatibility groups*: two versions in
the same group are interchangeable (it unifies them), versions in different groups are
incompatible (they may coexist under a [conflict policy](resolver.md)). For SemVer
this is the Cargo rule — the **major** for `major >= 1`, the **minor** for `0.y`, the
**patch** for `0.0.z`. For the `opaque` scheme every distinct version is its own group.

## Version schemes & opaque versions

A core declares a *version scheme* via [`[package].scheme`](manifest.md) — `semver`
(default) or `opaque`:

- **`semver`** — full SemVer 2.0.0 as above; a non-SemVer `version` is rejected at
  parse.
- **`opaque`** — the version is a non-SemVer token (a vendor part number `D5020100`,
  calver `2024.1`, `r3`), represented by **`OpaqueVersion`**. It has *no* precedence
  (only a deterministic lexical order for stable output), so dependents must pin an
  **exact** version (`=D5020100`); a range like `^D5020100` is rejected. A constraint
  whose operand is a non-SemVer token parses as an opaque exact pin
  (`constraint.opaque`).

`OpaqueVersion.parse(text)` validates the token (raising `InvalidVersionError`);
`str()` round-trips it. `AnyVersion = Version | OpaqueVersion` is the union a
[`Vlnv`](identity.md) may carry. Opaque versions still round-trip through the
[lockfile](lockfile.md) via a `scheme` marker. (An *ordered* non-SemVer scheme —
calver/monotonic precedence so such versions could be ranged — is a tracked open
issue.)

## Errors

`InvalidVersionError` and `InvalidConstraintError` (both subclasses of
`HdlPackagerError` and `ValueError`). See [exceptions](exceptions.md).

## Example

```python
from hdl_ip_packager import Version, VersionConstraint

v = Version.parse("1.4.0-rc.1")
assert v.is_prerelease and v.core == (1, 4, 0)

caret = VersionConstraint.parse("^1.2.0")
assert caret.matches(Version.parse("1.9.0"))
assert not caret.matches(Version.parse("2.0.0"))
assert not caret.matches(Version.parse("2.0.0-alpha"))  # pre-release rule

assert sorted([Version.parse(s) for s in ("1.0.0", "1.0.0-rc.1", "0.9.0")]) == [
    Version.parse("0.9.0"),
    Version.parse("1.0.0-rc.1"),
    Version.parse("1.0.0"),
]
```
