"""Automatic HDL name-mangling for multi-version coexistence.

When the resolver keeps two versions of one core (the ``isolate_namespaces`` conflict
policy), their declared units collide at elaboration: a ``package``/``module``/``entity``
name lives in one global namespace, so two ``package bus_pkg`` (or ``module fifo``)
declarations clash. This module rewrites each version's unit name to a version-unique
one (``bus_pkg`` -> ``bus_pkg_v1_1_0`` / ``bus_pkg_v2_0_0``) and rewrites every
consumer's references to the version *that consumer resolved to*, so both can build.

Handled, each with its own comment/string-aware lexer (so no full parser is needed):

* **SV packages** -- ``package <n>``, ``endpackage : <n>``, ``import <n>::``, ``<n>::``.
* **VHDL packages** (case-insensitive) -- ``package <n>`` / ``package body <n>``,
  ``end [package [body]] <n>``, ``use work.<n>``.
* **SV modules/programs** -- ``module``/``macromodule``/``program <n>``,
  ``endmodule : <n>``, and instantiations ``<n> [#( … )] <inst> [ […] ]* ( … )`` (incl.
  parameter maps, instance arrays, multiple instances, and generate-nested instances).
* **VHDL entities** -- ``entity <n>`` / ``architecture A of <n>`` / ``end [...] <n>`` /
  ``component <n>`` declarations, the direct instantiation ``entity work.<n>``, and the
  component instantiation ``label : [component] <n> [generic|port] map`` (incl.
  generate-nested).
* **SV interfaces** -- the ``interface <n>`` declaration, an instantiation, a port/var
  type ``<n> sig`` / ``virtual <n> v``, and a modport select ``<n>.<modport>``.

Because an SV module instantiation is not keyword-marked the way a package reference is,
module mangling is **classify-all-or-refuse**: a version is renamed only when *every*
occurrence of its name is provably a declaration, an instantiation, or an inert reference
-- otherwise the coexistence is refused (never a partial rewrite). See
``_reject_unclassifiable_sv_modules`` (and ``_reject_unclassifiable_sv_interfaces``).
(VHDL entity references are all keyword-marked, so any other occurrence is inert by
construction.) A colliding module/interface/entity name also declared by an *unrelated*
core is refused (``_reject_cross_ref_units``).

**Not** handled (refused with a clear message): any other source language; an SV
interface name in an unmodeled type context (e.g. a type-parameter default); and a
(System)Verilog macro that *constructs* a name by token pasting (its body is left
untouched).

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
    "declared_sv_interfaces",
    "declared_sv_modules",
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

# Mangleable unit kinds. Each kind has its own declaration scanner and reference
# position rules; the rewriter dispatches on the kind carried in a rename entry.
_PACKAGE = "package"
_MODULE = "module"  # SV module / macromodule / program: instantiation-only
_INTERFACE = "interface"  # SV interface: instantiation + type/virtual/modport refs
_ENTITY = "entity"  # VHDL entity: declaration + direct/component instantiation

# A rename entry: the version-unique mangled name plus the unit kind it applies to
# (so the rewriter knows which position rules to use for that name).
_Rename = tuple[str, str]  # (mangled_name, unit_kind)

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

    ``mangled_name("bus_pkg", Version(1, 1, 0))`` -> ``"bus_pkg_v1_1_0"``. The result
    must be a valid identifier in **both** SystemVerilog and VHDL, because a package
    name maps to a single mangled name shared by every consumer regardless of
    language. VHDL forbids consecutive underscores (and a leading/trailing one), so
    the suffix uses a single ``_v`` separator and any run of underscores is collapsed
    -- a single ``_`` is the only delimiter legal in both languages.
    """
    suffix = re.sub(r"[^0-9A-Za-z]", "_", str(version))
    return re.sub(r"_+", "_", f"{name}_v{suffix}").strip("_")


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
    """The module/interface/program names declared in *source* (all instantiable units)."""
    return (
        *_declared_after(source, "module"),
        *_declared_after(source, "interface"),
        *_declared_after(source, "program"),
    )


def declared_sv_modules(source: str) -> tuple[str, ...]:
    """The SV *module* names declared in *source* (``module``/``macromodule``/``program``).

    Programs instantiate like modules, so they share the ``module`` kind; interfaces are
    scanned separately (they have extra reference positions). See ``declared_sv_interfaces``.
    """
    return (
        *_declared_after(source, "module"),
        *_declared_after(source, "macromodule"),
        *_declared_after(source, "program"),
    )


def declared_sv_interfaces(source: str) -> tuple[str, ...]:
    """The SV *interface* names declared in *source* (``interface <name>``)."""
    return _declared_after(source, "interface")


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
    kinded = {name: (mangled, _PACKAGE) for name, mangled in renames.items()}
    return _rewrite(_tokens(source), kinded, _sv_position, fold=False)


def rewrite_vhdl_packages(source: str, renames: Mapping[str, str]) -> str:
    """Rewrite VHDL package declarations and references in *source* per *renames*.

    *renames* is keyed by **lowercased** package name (VHDL is case-insensitive).
    Rewrites only in unambiguous package positions: a ``package``/``package body``
    declaration, an ``end [...] <name>`` label, or a ``use work.<name>`` reference.
    """
    if not renames:
        return source
    kinded = {name: (mangled, _PACKAGE) for name, mangled in renames.items()}
    return _rewrite(_vhdl_tokens(source), kinded, _vhdl_position, fold=True)


# A position predicate decides whether the significant token at *position* is a
# rewritable position for a unit of the given *kind*.
_PositionPredicate = Callable[[Sequence[tuple[int, str, str]], int, str], bool]


def _rewrite(
    tokens: Sequence[tuple[str, str]],
    renames: Mapping[str, _Rename],
    is_position: _PositionPredicate,
    *,
    fold: bool,
) -> str:
    """Replace identifier tokens in a unit's positions per *renames* (case-fold if *fold*).

    *renames* maps a name to ``(mangled_name, kind)``; *is_position* is consulted with
    that kind so each name is rewritten only in the positions valid for its unit kind.
    """
    sig = _significant(tokens)
    position_of = {index: position for position, (index, _k, _t) in enumerate(sig)}
    out: list[str] = []
    for index, (tok_kind, text) in enumerate(tokens):
        key = text.lower() if fold else text
        entry = renames.get(key) if tok_kind == "ident" else None
        if entry is not None and is_position(sig, position_of[index], entry[1]):
            out.append(entry[0])
        else:
            out.append(text)
    return "".join(out)


def _sv_position(sig: Sequence[tuple[int, str, str]], position: int, kind: str) -> bool:
    """Whether the SV significant token at *position* is a rewritable position for *kind*."""
    if kind == _PACKAGE:
        return _is_sv_package_position(sig, position)
    if kind == _MODULE:
        return _is_sv_module_position(sig, position)
    if kind == _INTERFACE:
        return _is_sv_interface_position(sig, position)
    return False


def _skip_group(
    sig: Sequence[tuple[int, str, str]], i: int, open_ch: str, close_ch: str
) -> int | None:
    """Index just after the *open_ch*…*close_ch* group starting at ``sig[i]`` (or None)."""
    depth = 0
    while i < len(sig):
        text = sig[i][2]
        if text == open_ch:
            depth += 1
        elif text == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _sv_module_decl_position(sig: Sequence[tuple[int, str, str]], position: int) -> bool:
    """True if ``sig[position]`` is an SV module/program declaration name or end label."""
    prev = sig[position - 1][2] if position >= 1 else None
    if prev in ("module", "macromodule", "program"):
        return True
    prev_prev = sig[position - 2][2] if position >= 2 else None
    return prev == ":" and prev_prev in ("endmodule", "endprogram")  # `endmodule : <name>`


def _sv_instantiation_position(sig: Sequence[tuple[int, str, str]], position: int) -> bool:
    """True if ``sig[position]`` begins a module/interface instantiation.

    Matches ``<name> [#( … )] <instance> [ [ … ] ]* (`` -- an optional parameter map,
    an instance-name identifier, optional packed/unpacked ranges, then ``(``. This is
    the shape that distinguishes an instantiation from a call (``name(...)`` -- no
    instance name) or a declaration (no trailing ``(``). Generate-nested instantiations
    have the same shape, so they match here too.
    """
    i = position + 1
    if i < len(sig) and sig[i][2] == "#":  # optional parameter map: #( ... )
        i += 1
        if i >= len(sig) or sig[i][2] != "(":
            return False
        nxt = _skip_group(sig, i, "(", ")")
        if nxt is None:
            return False
        i = nxt
    if i >= len(sig) or sig[i][1] != "ident":  # instance name
        return False
    i += 1
    while i < len(sig) and sig[i][2] == "[":  # optional instance-array range(s)
        nxt = _skip_group(sig, i, "[", "]")
        if nxt is None:
            return False
        i = nxt
    return i < len(sig) and sig[i][2] == "("  # the port-connection list


def _is_sv_module_position(sig: Sequence[tuple[int, str, str]], position: int) -> bool:
    """True if ``sig[position]`` is a rewritable SV module position (declaration or use)."""
    return _sv_module_decl_position(sig, position) or _sv_instantiation_position(sig, position)


def _is_sv_interface_position(sig: Sequence[tuple[int, str, str]], position: int) -> bool:
    """True if ``sig[position]`` is a rewritable SV interface position.

    An interface name is also a *type*, so it is rewritten in more places than a module:
    the ``interface <n>`` / ``endinterface : <n>`` declaration; an instantiation
    ``<n> <inst> (…)``; a port/variable type ``<n> <sig>`` or ``virtual <n> <vif>`` (both
    ``<n>`` directly before an identifier); and a modport select ``<n>.<modport>``
    (``<n>`` directly before ``.``). A member access ``x.<n>`` (``<n>`` after ``.``) is
    inert and left untouched.
    """
    prev = sig[position - 1][2] if position >= 1 else None
    prev_prev = sig[position - 2][2] if position >= 2 else None
    if prev == "interface":  # declaration
        return True
    if prev == ":" and prev_prev == "endinterface":  # end label
        return True
    if prev == ".":  # member access `x.<n>` -> inert
        return False
    following = sig[position + 1] if position + 1 < len(sig) else None
    if following is None:
        return False
    if following[2] == ".":  # modport select `<n>.<modport>`
        return True
    return following[1] == "ident"  # instantiation `<n> u (…)` or type `<n> sig` / `virtual <n> v`


def _vhdl_position(sig: Sequence[tuple[int, str, str]], position: int, kind: str) -> bool:
    """Whether the VHDL significant token at *position* is a rewritable position for *kind*."""
    if kind == _PACKAGE:
        return _is_vhdl_package_position(sig, position)
    if kind == _ENTITY:
        return _is_vhdl_entity_position(sig, position)
    return False


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


def _is_vhdl_entity_position(sig: Sequence[tuple[int, str, str]], position: int) -> bool:
    """True if the VHDL significant token at *position* is an entity declaration or reference.

    Covers ``entity N is`` / ``architecture A of N`` / ``configuration C of N`` / ``end [...] N``
    / ``component N`` declarations, the direct instantiation ``entity work.N`` (incl.
    ``use entity work.N``), and the component instantiation ``label : [component] N
    [generic|port] map`` / ``label : N use ...`` / ``label : N;``. Generate-nested
    instantiations have the same shape, so they match here too. An entity name cannot be a
    value in VHDL, so any other occurrence (a label ``N :``, a selected/named-library name
    ``x.N``) is inert and left untouched.
    """
    prev = sig[position - 1][2].lower() if position >= 1 else None
    prev2 = sig[position - 2][2].lower() if position >= 2 else None
    prev3 = sig[position - 3][2].lower() if position >= 3 else None
    nxt = sig[position + 1][2].lower() if position + 1 < len(sig) else None
    if prev in ("entity", "component", "end"):  # decl / end label / `component N`
        return True
    if prev == "of" and prev3 in ("architecture", "configuration"):  # `... of N`
        return True
    if prev == "." and prev2 == "work":  # direct instantiation `entity work.N`
        return True
    # component instantiation `label : [component] N [generic|port] map` / `: N use` / `: N;`
    return prev == ":" and nxt in ("port", "generic", "use", ";")


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

    def declared_by_kind(self) -> dict[str, set[str]]:
        """The names this file declares, grouped by mangleable unit kind."""
        if self.language in _SV_LANGUAGES:
            return {
                _PACKAGE: set(declared_packages(self.text)),
                _MODULE: set(declared_sv_modules(self.text)),
                _INTERFACE: set(declared_sv_interfaces(self.text)),
            }
        if self.language == _VHDL_LANGUAGE:
            return {
                _PACKAGE: set(declared_vhdl_packages(self.text)),
                _ENTITY: set(declared_vhdl_entities(self.text)),
            }
        return {}

    def rewrite(self, renames: Mapping[str, _Rename]) -> str:
        """Rewrite this file's unit names per *renames* (by its language).

        *renames* maps a name to ``(mangled_name, kind)``; the rewriter applies the
        position rules for each name's kind in this file's language.
        """
        if not renames:
            return self.text
        if self.language in _SV_LANGUAGES:
            return _rewrite(_tokens(self.text), renames, _sv_position, fold=False)
        if self.language == _VHDL_LANGUAGE:
            return _rewrite(_vhdl_tokens(self.text), renames, _vhdl_position, fold=True)
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
    """Plan the unit renames needed to let coexisting versions build together.

    Handles colliding **packages** (SV + VHDL), **SV modules/programs**, **SV
    interfaces**, and **VHDL entities**. Returns a :class:`ManglePlan` whose ``rewritten``
    maps every source file's key to its (possibly unchanged) text. Raises
    :class:`BackendError` when a conflict cannot be mangled safely -- a source whose
    language the mangler does not handle, an unclassifiable module/interface occurrence, a
    name also declared by an unrelated core, or two versions that mangle to the same name.
    """
    by_ref: dict[PackageRef, list[GenCore]] = {}
    for core in cores:
        by_ref.setdefault(core.manifest.ref, []).append(core)
    conflicted = {ref: group for ref, group in by_ref.items() if len(group) > 1}

    owner_of: dict[str, PackageRef] = {}  # colliding unit name -> the ref it belongs to
    kind_of: dict[str, str] = {}  # colliding unit name -> its unit kind
    declares: dict[str, set[str]] = {}  # VLNV string -> the unit names it declares
    sv_module_collisions: set[str] = set()
    sv_interface_collisions: set[str] = set()
    for ref, group in conflicted.items():
        _reject_unknown_language(ref, group)
        declared_per_version: list[dict[str, set[str]]] = []
        for core in group:
            by_kind: dict[str, set[str]] = {}
            for source in core.files:
                for kind, names in source.declared_by_kind().items():
                    by_kind.setdefault(kind, set()).update(names)
            declares[str(core.manifest.vlnv)] = {n for names in by_kind.values() for n in names}
            declared_per_version.append(by_kind)
        for kind in (_PACKAGE, _MODULE, _INTERFACE, _ENTITY):
            counts = Counter(
                name for by_kind in declared_per_version for name in by_kind.get(kind, set())
            )
            colliding = sorted(name for name, count in counts.items() if count >= 2)
            for name in colliding:
                owner_of[name] = ref
                kind_of[name] = kind
            if kind == _MODULE:
                sv_module_collisions.update(colliding)
            elif kind == _INTERFACE:
                sv_interface_collisions.update(colliding)
    _reject_cross_ref_units(cores, owner_of, kind_of)
    _reject_unclassifiable_sv_modules(cores, sv_module_collisions)
    _reject_unclassifiable_sv_interfaces(cores, sv_interface_collisions)

    rewritten: dict[tuple[str, str], str] = {}
    renamed: dict[str, set[str]] = {name: set() for name in owner_of}
    for core in cores:
        rename_map = _rename_map_for(core, owner_of, kind_of, declares, conflicted, renamed)
        for source in core.files:
            rewritten[source.key] = source.rewrite(rename_map)
    _reject_colliding_mangled_names(owner_of, declares, conflicted, renamed)
    return ManglePlan(
        rewritten=rewritten,
        renamed={name: tuple(sorted(mangled)) for name, mangled in renamed.items()},
    )


def _reject_colliding_mangled_names(
    owner_of: Mapping[str, PackageRef],
    declares: Mapping[str, set[str]],
    conflicted: Mapping[PackageRef, Sequence[GenCore]],
    renamed: Mapping[str, set[str]],
) -> None:
    """Refuse if two versions of a package mangle to the *same* identifier.

    ``mangled_name`` collapses underscore runs to stay VHDL-legal, so a pathological
    version string (e.g. an opaque tag with adjacent separators like ``1..0`` vs ``1.0``)
    could map two distinct versions to one name. That would silently reintroduce the very
    collision mangling exists to prevent, so fail closed instead of emitting broken HDL.
    """
    for name, ref in owner_of.items():
        versions = {
            str(core.manifest.vlnv.version)
            for core in conflicted[ref]
            if name in declares[str(core.manifest.vlnv)]
        }
        if len(renamed[name]) < len(versions):
            raise BackendError(
                f"Cannot coexist versions of package {name!r}: their mangled names collide "
                f"({sorted(renamed[name])}) -- the version strings differ only by separators "
                f"that the HDL-safe name flattens. Use distinct version strings, or resolve "
                f"to a single version."
            )


def _reject_unknown_language(ref: PackageRef, group: Sequence[GenCore]) -> None:
    """Refuse a conflict whose sources are in a language the mangler does not handle."""
    handled = _SV_LANGUAGES | {_VHDL_LANGUAGE}
    if any(f.language not in handled for core in group for f in core.files):
        raise BackendError(
            f"Cannot coexist two versions of {ref}: it has sources in a language the mangler "
            f"does not handle (only SystemVerilog and VHDL are supported). Resolve to a single "
            f"version (e.g. [resolution] on-conflict = 'use_latest')."
        )


def _reject_unclassifiable_sv_interfaces(cores: Sequence[GenCore], names: set[str]) -> None:
    """Refuse if any SV source uses a colliding interface name in an unclassifiable position.

    An interface reference is always ``<name>`` directly before an identifier (an
    instantiation or a port/variable/``virtual`` type) or before ``.`` (a modport select);
    a declaration or an ``x.<name>`` member are the other classifiable cases. Any other
    occurrence -- e.g. an interface name as a type-parameter default ``#(type T = <name>)``
    -- is a context the rewriter does not model, so refuse rather than risk a dangling
    reference.
    """
    if not names:
        return
    for core in cores:
        for source in core.files:
            if source.language not in _SV_LANGUAGES:
                continue
            sig = _significant(_tokens(source.text))
            for position, (_index, tok_kind, text) in enumerate(sig):
                if tok_kind != "ident" or text not in names:
                    continue
                if _is_sv_interface_position(sig, position):
                    continue  # declaration / instantiation / type / modport -> rewritten
                if position >= 1 and sig[position - 1][2] == ".":
                    continue  # member access x.<name> -> inert
                raise BackendError(
                    f"Cannot coexist versions of interface {text!r}: it appears in "
                    f"{source.key[1]!r} in a position the mangler cannot classify (near "
                    f"'{text}'). Resolve to a single version, or expose the shared logic as "
                    f"a package."
                )


def _reject_cross_ref_units(
    cores: Sequence[GenCore], owner_of: Mapping[str, PackageRef], kind_of: Mapping[str, str]
) -> None:
    """Refuse a colliding *module*/*entity* name also declared by an unrelated core.

    Mangling keys a colliding name to the ref whose versions collide on it. If a *different*
    core declares the same module/entity name, that name is ambiguous across cores --
    renaming it would corrupt the unrelated core -- so refuse rather than guess. (Realistic
    designs give each unit a unique name; this guards the accidental clash.)
    """
    for name, owner_ref in owner_of.items():
        kind = kind_of[name]
        if kind not in (_MODULE, _ENTITY, _INTERFACE):
            continue
        for core in cores:
            if core.manifest.ref == owner_ref:
                continue
            declared = {n for f in core.files for n in f.declared_by_kind().get(kind, set())}
            if name in declared:
                raise BackendError(
                    f"Cannot coexist versions of {kind} {name!r}: it is also declared by "
                    f"{core.manifest.ref} (a different core), so the name is ambiguous across "
                    f"cores. Rename one of them, or resolve to a single version."
                )


def _reject_unclassifiable_sv_modules(cores: Sequence[GenCore], names: set[str]) -> None:
    """Refuse if any SV source uses a colliding module name in an unclassifiable position.

    A module name may only legally appear as a declaration, an instantiation, or an inert
    coincidence (a hierarchical member ``x.<name>`` or the name used as a plain value).
    An occurrence that is none of those -- in particular ``<name> <identifier>`` that is
    not a full instantiation -- *might* be an instantiation form we do not model, so we
    refuse rather than risk renaming the declaration while leaving a live reference.
    """
    if not names:
        return
    for core in cores:
        for source in core.files:
            if source.language not in _SV_LANGUAGES:
                continue
            sig = _significant(_tokens(source.text))
            for position, (_index, tok_kind, text) in enumerate(sig):
                if tok_kind != "ident" or text not in names:
                    continue
                if _is_sv_module_position(sig, position):
                    continue  # declaration or instantiation -> will be rewritten
                prev = sig[position - 1][2] if position >= 1 else None
                if prev == ".":
                    continue  # hierarchical member -> inert
                following = sig[position + 1] if position + 1 < len(sig) else None
                if following is None or following[1] != "ident":
                    continue  # used as a plain value/operand -> inert
                raise BackendError(
                    f"Cannot coexist versions of module {text!r}: it appears in "
                    f"{source.key[1]!r} in a position the mangler cannot classify as a "
                    f"declaration, an instantiation, or an inert reference (near "
                    f"'{text} {following[2]}'). Resolve to a single version, or expose the "
                    f"shared logic as a package."
                )


def _rename_map_for(
    core: GenCore,
    owner_of: Mapping[str, PackageRef],
    kind_of: Mapping[str, str],
    declares: Mapping[str, set[str]],
    conflicted: Mapping[PackageRef, Sequence[GenCore]],
    renamed: dict[str, set[str]],
) -> dict[str, _Rename]:
    """The unit renames to apply to *core*'s sources (records them in *renamed*).

    Each entry maps a name to ``(mangled_name, kind)``: a core that *declares* a
    colliding unit renames it to its own version; a core that *uses* it renames to the
    version that core resolved to.
    """
    rename_map: dict[str, _Rename] = {}
    own = declares.get(str(core.manifest.vlnv), set())
    for name, owner_ref in owner_of.items():
        if core.manifest.ref == owner_ref and name in own:  # a version that declares the unit
            mangled = mangled_name(name, core.manifest.vlnv.version)
        else:  # this core *uses* the unit -> rewrite to the version it resolved to
            used = _resolved_version(core.manifest, owner_ref, conflicted[owner_ref])
            if used is None:
                continue
            mangled = mangled_name(name, used.version)
        rename_map[name] = (mangled, kind_of[name])
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
