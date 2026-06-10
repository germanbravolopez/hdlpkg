"""Automatic HDL **package** name-mangling for multi-version coexistence.

When the resolver keeps two versions of one package (the ``isolate_namespaces``
conflict policy), they collide at elaboration: a ``package`` name lives in one global
namespace, so two ``package bus_pkg`` declarations clash. This module rewrites each
version's package name to a version-unique one (``bus_pkg`` -> ``bus_pkg__v1_1_0`` /
``bus_pkg__v2_0_0``) and rewrites every consumer's references to the version *that
consumer resolved to*, so both can build.

Both **SystemVerilog/Verilog** and **VHDL** packages are handled, each with its own
comment/string-aware lexer, because the package-reference contexts are syntactically
unambiguous (so no full parser is needed):

* SystemVerilog -- ``package <name>``, ``endpackage : <name>``, ``import <name>::``,
  and ``<name>::`` scoped references.
* VHDL (case-insensitive) -- ``package <name>`` / ``package body <name>``,
  ``end [package [body]] <name>``, and ``use work.<name>...`` references.

**Not** handled (and refused upstream): two versions of a *module*/*interface* (SV) or
*entity* (VHDL) -- their instantiation position is ambiguous without a real parser;
any other source language; and a (System)Verilog macro that *constructs* a package
name by token pasting (its body is left untouched and will not be mangled).

This module is **pure**: it operates on source text passed in by the caller, so the
filesystem work (reading sources, writing the rewritten tree) stays in the CLI.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from .exceptions import BackendError
from .manifest import Manifest
from .version import AnyVersion
from .vlnv import PackageRef, Vlnv

__all__ = [
    "GenCore",
    "GenSourceFile",
    "ManglePlan",
    "declared_modules",
    "declared_packages",
    "declared_vhdl_entities",
    "declared_vhdl_packages",
    "mangled_name",
    "plan_package_mangling",
    "rewrite_sv_packages",
    "rewrite_vhdl_packages",
]

# Source languages the mangler can rewrite. ``GenSourceFile.language`` is the
# normalized fileset kind, lowercased.
_SV_LANGUAGES = frozenset({"systemverilog", "verilog"})
_VHDL_LANGUAGE = "vhdl"

# A comment/string-aware token scan. Order matters: comments and strings are matched
# before identifiers so their contents are never treated as code.
_TOKEN_RE = re.compile(
    r"""
      (?P<lcomment>//[^\n]*)
    | (?P<bcomment>/\*.*?\*/)
    | (?P<string>"(?:\\.|[^"\\])*")
    | (?P<directive>`[A-Za-z_]\w*)
    | (?P<escaped>\\[^\s]+)
    | (?P<dcolon>::)
    | (?P<ident>[A-Za-z_][\w$]*)
    | (?P<ws>\s+)
    | (?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)

_TRIVIA = frozenset({"ws", "lcomment", "bcomment"})

# A VHDL token scan: ``--`` line comments (and 2008 ``/* */`` blocks), strings (a
# doubled ``""`` escapes a quote), character literals, extended identifiers, and plain
# identifiers. VHDL is case-insensitive, so callers fold identifiers to compare.
_VHDL_TOKEN_RE = re.compile(
    r"""
      (?P<lcomment>--[^\n]*)
    | (?P<bcomment>/\*.*?\*/)
    | (?P<string>"(?:""|[^"])*")
    | (?P<char>'[^']')
    | (?P<extended>\\[^\\]*\\)
    | (?P<ident>[A-Za-z][A-Za-z0-9_]*)
    | (?P<ws>\s+)
    | (?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)


def _vhdl_tokens(source: str) -> list[tuple[str, str]]:
    """Scan *source* (VHDL) into ``(kind, text)`` tokens covering it exactly."""
    return [(m.lastgroup or "other", m.group()) for m in _VHDL_TOKEN_RE.finditer(source)]


def mangled_name(name: str, version: AnyVersion) -> str:
    """Return *name* suffixed with a version-unique, HDL-safe tag.

    ``mangled_name("bus_pkg", Version(1, 1, 0))`` -> ``"bus_pkg__v1_1_0"``. The result
    is a valid identifier in both SystemVerilog and VHDL.
    """
    suffix = re.sub(r"[^0-9A-Za-z]", "_", str(version))
    return f"{name}__v{suffix}"


def _tokens(source: str) -> list[tuple[str, str]]:
    """Scan *source* into ``(kind, text)`` tokens covering it exactly."""
    return [(m.lastgroup or "other", m.group()) for m in _TOKEN_RE.finditer(source)]


def _significant(tokens: Sequence[tuple[str, str]]) -> list[tuple[int, str, str]]:
    """The non-trivia tokens as ``(index, kind, text)`` (comments/whitespace dropped)."""
    return [(i, kind, text) for i, (kind, text) in enumerate(tokens) if kind not in _TRIVIA]


def _declared_after(source: str, keyword: str) -> tuple[str, ...]:
    """The identifier names declared immediately after *keyword* (e.g. ``package``)."""
    sig = _significant(_tokens(source))
    names: list[str] = []
    for position, (_index, _kind, text) in enumerate(sig):
        if text == keyword and position + 1 < len(sig):
            _ni, next_kind, next_text = sig[position + 1]
            if next_kind == "ident":
                names.append(next_text)
    return tuple(names)


def declared_packages(source: str) -> tuple[str, ...]:
    """The SystemVerilog package names declared (``package <name>;``) in *source*."""
    return _declared_after(source, "package")


def declared_modules(source: str) -> tuple[str, ...]:
    """The module/interface/program names declared in *source* (for the refusal check)."""
    return (
        *_declared_after(source, "module"),
        *_declared_after(source, "interface"),
        *_declared_after(source, "program"),
    )


def _vhdl_declared_after(source: str, keyword: str, *, skip_dotted: bool) -> tuple[str, ...]:
    """VHDL names declared after *keyword* (case-insensitive), lowercased.

    With *skip_dotted* a name immediately followed by ``.`` is skipped, so an
    ``entity work.foo`` reference is not mistaken for an ``entity foo is`` declaration.
    """
    sig = _significant(_vhdl_tokens(source))
    names: set[str] = set()
    for position, (_index, _kind, text) in enumerate(sig):
        if text.lower() != keyword or position + 1 >= len(sig):
            continue
        _ni, next_kind, next_text = sig[position + 1]
        following = sig[position + 2][2] if position + 2 < len(sig) else None
        if next_kind == "ident" and not (skip_dotted and following == "."):
            names.add(next_text.lower())
    return tuple(sorted(names))


def declared_vhdl_packages(source: str) -> tuple[str, ...]:
    """The VHDL package names declared (``package <name>``, lowercased) in *source*.

    Covers ``package <name> is`` and ``package body <name> is`` (a ``body`` token is
    skipped so the body's package name is still collected).
    """
    names: set[str] = set()
    sig = _significant(_vhdl_tokens(source))
    for position, (_index, _kind, text) in enumerate(sig):
        if text.lower() != "package" or position + 1 >= len(sig):
            continue
        _ni, next_kind, next_text = sig[position + 1]
        if next_kind == "ident" and next_text.lower() != "body":
            names.add(next_text.lower())
        elif next_text.lower() == "body" and position + 2 < len(sig):
            _bi, body_kind, body_text = sig[position + 2]
            if body_kind == "ident":
                names.add(body_text.lower())
    return tuple(sorted(names))


def declared_vhdl_entities(source: str) -> tuple[str, ...]:
    """The VHDL entity names declared (``entity <name> is``, lowercased; refusal check)."""
    return _vhdl_declared_after(source, "entity", skip_dotted=True)


def rewrite_sv_packages(source: str, renames: Mapping[str, str]) -> str:
    """Rewrite SystemVerilog package declarations and references in *source* per *renames*.

    Rewrites an identifier in ``renames`` only in an unambiguous package position: a
    ``package``/``endpackage`` declaration or label, or immediately before ``::`` (a
    scoped reference or ``import``). Occurrences in comments, strings, or any other
    position are left untouched. Returns the rewritten text (unchanged if nothing
    matched).
    """
    if not renames:
        return source
    return _rewrite(_tokens(source), renames, _is_sv_package_position, fold=False)


def rewrite_vhdl_packages(source: str, renames: Mapping[str, str]) -> str:
    """Rewrite VHDL package declarations and references in *source* per *renames*.

    *renames* is keyed by **lowercased** package name (VHDL is case-insensitive).
    Rewrites only in unambiguous package positions: a ``package``/``package body``
    declaration, an ``end [...] <name>`` label, or a ``use work.<name>`` reference.
    """
    if not renames:
        return source
    return _rewrite(_vhdl_tokens(source), renames, _is_vhdl_package_position, fold=True)


_PositionPredicate = Callable[[Sequence[tuple[int, str, str]], int], bool]


def _rewrite(
    tokens: Sequence[tuple[str, str]],
    renames: Mapping[str, str],
    is_position: _PositionPredicate,
    *,
    fold: bool,
) -> str:
    """Replace identifier tokens in package positions per *renames* (case-fold if *fold*)."""
    sig = _significant(tokens)
    position_of = {index: position for position, (index, _k, _t) in enumerate(sig)}
    out: list[str] = []
    for index, (kind, text) in enumerate(tokens):
        key = text.lower() if fold else text
        if kind == "ident" and key in renames and is_position(sig, position_of[index]):
            out.append(renames[key])
        else:
            out.append(text)
    return "".join(out)


def _is_sv_package_position(sig: Sequence[tuple[int, str, str]], position: int) -> bool:
    """True if the significant token at *position* is an SV package declaration/reference."""
    next_text = sig[position + 1][2] if position + 1 < len(sig) else None
    if next_text == "::":  # scoped reference or `import <name>::`
        return True
    prev_text = sig[position - 1][2] if position >= 1 else None
    if prev_text in ("package", "endpackage"):
        return True
    # `endpackage : <name>` end label
    prev_prev = sig[position - 2][2] if position >= 2 else None
    return prev_text == ":" and prev_prev == "endpackage"


def _is_vhdl_package_position(sig: Sequence[tuple[int, str, str]], position: int) -> bool:
    """True if the significant token at *position* is a VHDL package declaration/reference."""
    prev = sig[position - 1][2].lower() if position >= 1 else None
    prev_prev = sig[position - 2][2].lower() if position >= 2 else None
    if prev in ("package", "end"):  # `package N`, `end N`, `end package N`
        return True
    if prev == "body" and prev_prev == "package":  # `package body N` / `end package body N`
        return True
    return prev == "." and prev_prev == "work"  # `use work.N...` reference


# --------------------------------------------------------------------------- plan


@dataclass(frozen=True)
class GenSourceFile:
    """One source file taking part in generation: its key, text, and HDL language."""

    key: tuple[str, str]  # (owning VLNV string, fileset-relative path) -- a stable id
    text: str
    language: str  # normalized, lowercased: "systemverilog" / "verilog" / "vhdl" / other

    def declared_package_names(self) -> set[str]:
        """The package names this file declares (empty for an unmangleable language)."""
        if self.language in _SV_LANGUAGES:
            return set(declared_packages(self.text))
        if self.language == _VHDL_LANGUAGE:
            return set(declared_vhdl_packages(self.text))
        return set()

    def declared_unit_names(self) -> set[str]:
        """The *non-package* unit names (SV module/interface, VHDL entity) -- refusal check."""
        if self.language in _SV_LANGUAGES:
            return set(declared_modules(self.text))
        if self.language == _VHDL_LANGUAGE:
            return set(declared_vhdl_entities(self.text))
        return set()

    def rewrite(self, renames: Mapping[str, str]) -> str:
        """Rewrite this file's package names per *renames* (by its language)."""
        if self.language in _SV_LANGUAGES:
            return rewrite_sv_packages(self.text, renames)
        if self.language == _VHDL_LANGUAGE:
            return rewrite_vhdl_packages(self.text, renames)
        return self.text


@dataclass(frozen=True)
class GenCore:
    """A core taking part in generation: its manifest and its (already-read) sources."""

    manifest: Manifest
    files: tuple[GenSourceFile, ...]


@dataclass(frozen=True)
class ManglePlan:
    """The result of planning a mangle: rewritten sources plus a human-readable report."""

    rewritten: Mapping[tuple[str, str], str]  # source key -> rewritten text
    renamed: Mapping[str, tuple[str, ...]]  # original package name -> sorted mangled names


def plan_package_mangling(cores: Sequence[GenCore]) -> ManglePlan:
    """Plan the package renames needed to let coexisting versions build together.

    Returns a :class:`ManglePlan` whose ``rewritten`` maps every source file's key to
    its (possibly unchanged) text. Raises :class:`BackendError` when a conflict cannot
    be mangled safely -- two versions of a *module*/interface (SV) or *entity* (VHDL),
    or a source whose language the mangler does not handle.
    """
    by_ref: dict[PackageRef, list[GenCore]] = {}
    for core in cores:
        by_ref.setdefault(core.manifest.ref, []).append(core)
    conflicted = {ref: group for ref, group in by_ref.items() if len(group) > 1}

    owner_of: dict[str, PackageRef] = {}  # colliding package name -> the ref it belongs to
    declares: dict[str, set[str]] = {}  # VLNV string -> the package names it declares
    for ref, group in conflicted.items():
        _reject_unmangleable(ref, group)
        per_version: dict[str, set[str]] = {}
        for core in group:
            names = {n for f in core.files for n in f.declared_package_names()}
            declares[str(core.manifest.vlnv)] = names
            per_version[str(core.manifest.vlnv)] = names
        counts = Counter(name for names in per_version.values() for name in names)
        for name, count in counts.items():
            if count >= 2:  # the same package name declared by two versions -> collides
                owner_of[name] = ref

    rewritten: dict[tuple[str, str], str] = {}
    renamed: dict[str, set[str]] = {name: set() for name in owner_of}
    for core in cores:
        rename_map = _rename_map_for(core, owner_of, declares, conflicted, renamed)
        for source in core.files:
            rewritten[source.key] = source.rewrite(rename_map)
    return ManglePlan(
        rewritten=rewritten,
        renamed={name: tuple(sorted(mangled)) for name, mangled in renamed.items()},
    )


def _reject_unmangleable(ref: PackageRef, group: Sequence[GenCore]) -> None:
    """Refuse a conflict the package mangler cannot handle: an unknown language, or a
    colliding non-package unit (SV module/interface, VHDL entity)."""
    handled = _SV_LANGUAGES | {_VHDL_LANGUAGE}
    if any(f.language not in handled for core in group for f in core.files):
        raise BackendError(
            f"Cannot coexist two versions of {ref}: it has sources in a language the package "
            f"mangler does not handle (only SystemVerilog and VHDL packages are supported). "
            f"Resolve to a single version (e.g. [resolution] on-conflict = 'use_latest')."
        )
    unit_counts = Counter(
        name for core in group for f in core.files for name in f.declared_unit_names()
    )
    clashing = sorted(name for name, count in unit_counts.items() if count >= 2)
    if clashing:
        raise BackendError(
            f"Cannot coexist two versions of {ref}: they declare colliding module/entity "
            f"name(s) {clashing}, and automatic name-mangling is only implemented for "
            f"packages. Resolve to a single version or split the build."
        )


def _rename_map_for(
    core: GenCore,
    owner_of: Mapping[str, PackageRef],
    declares: Mapping[str, set[str]],
    conflicted: Mapping[PackageRef, Sequence[GenCore]],
    renamed: dict[str, set[str]],
) -> dict[str, str]:
    """The package renames to apply to *core*'s sources (records them in *renamed*)."""
    rename_map: dict[str, str] = {}
    own = declares.get(str(core.manifest.vlnv), set())
    for name, owner_ref in owner_of.items():
        if name in own:  # this core *is* a version that declares the package
            mangled = mangled_name(name, core.manifest.vlnv.version)
        else:  # this core *uses* the package -> rewrite to the version it resolved to
            used = _resolved_version(core.manifest, owner_ref, conflicted[owner_ref])
            if used is None:
                continue
            mangled = mangled_name(name, used.version)
        rename_map[name] = mangled
        renamed[name].add(mangled)
    return rename_map


def _resolved_version(
    consumer: Manifest, ref: PackageRef, present: Sequence[GenCore]
) -> Vlnv | None:
    """Which present version of *ref* the *consumer* resolved to (None if it has no dep)."""
    constraints = [dep.constraint for dep in consumer.dependencies if dep.ref == ref]
    if not constraints:
        return None
    versions = [core.manifest.vlnv for core in present]
    matching = [v for v in versions if all(c.matches(v.version) for c in constraints)] or versions
    return max(matching, key=lambda v: v.version)
