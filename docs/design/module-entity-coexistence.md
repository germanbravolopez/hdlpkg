# Design proposal — module/entity multi-version coexistence (0.12.0)

**Status:** **implemented** (landed on `develop` for 0.12.0) via approach **A**
(in-house, zero-dep). **Scope delivered:** SystemVerilog *modules*, *interfaces*, and
*programs* **and** VHDL *entities*, including **instantiations nested in `generate`
statements** (both languages), with the classify-all-or-refuse safety model and a
cross-ref guard. Exercised end to end by `tests/unit/test_mangle.py`,
`tests/integration/test_mangle_unit_gen_cli.py`, and the consumer demo's `soc_modver`
example built in real Verilator on CI. Reviewer decisions are in
[§12](#12-reviewer-decisions); this doc is retained as the design record.

---

## 1. Goal

Today, under `[resolution] on-conflict = "isolate_namespaces"`, `gen` lets two
incompatible versions of a shared **package** coexist in one elaboration by
name-mangling the package and every reference to it ([mangle.py](https://github.com/germanbravolopez/hdlpkg/blob/main/src/hdlpkg/mangle.py)).
Two versions of a shared **module** (SV) or **entity** (VHDL) are still **refused**
(`_reject_unmangleable`). This proposal lifts that refusal: coexisting module/entity
versions get the same per-version name-mangling, so both elaborate side by side.

No `ip.toml` / `ip.lock` / CLI change — this is entirely inside `gen`'s mangling pass.

## 2. Why packages were easy and units are not

The package mangler works because every package *reference* sits in a position the
comment/string-aware lexer can identify **unambiguously** without a grammar:

- SV: `package <n>` / `endpackage : <n>` / `import <n>::` / `<n>::`
- VHDL: `package <n>` / `package body <n>` / `end [...] <n>` / `use work.<n>`

A **module instantiation** has no such marker. `foo u_foo (...)` leads with the module
name itself — indistinguishable, token-by-token, from other constructs unless we model
the instantiation grammar. That is the gap that made us refuse it (and file the
"source-unit tokenizing" backlog item).

## 3. Design principles (non-negotiable)

1. **Never emit broken HDL.** A mangled declaration with a *missed* reference is worse
   than a clean refusal — it fails (or mis-elaborates) at tool time. So the bar is
   higher than for packages.
2. **Classify-all-or-refuse** (the core safety idea, §6). We rename a unit only if
   *every* occurrence of its name in *every* source can be classified as a known,
   safe position. One unclassifiable occurrence → refuse that coexistence (today's
   behavior), never a partial rewrite.
3. **Refuse > corrupt.** Anything the rewriter cannot prove safe stays refused. This
   means the feature is *incremental coverage* over today's blanket refusal — there is
   no regression risk to existing designs.
4. **Stay pure and dependency-free.** The mangler is pure text-in/text-out; the CLI
   does the I/O. Keep `dependencies = []`.

## 4. Approach decision

> **Decision: A, confirmed by the reviewer** (flexibility + the ability to grow the
> rewriter ourselves later). B is recorded below for context.

### A — In-house scoped rewriter (chosen)

Extend the existing token machinery to recognize the **declaration** and
**instantiation** positions of *known colliding names only*, plus a **classifier**
that proves every other occurrence is safe (or refuses). We are **not** building a
general HDL parser — we recognize a constrained set of shapes for a known, small set
of names, and refuse the rest.

- **Pros:** zero new dependencies; preserves the "plain Python 3.11+, no lock-in"
  promise; small, reviewable, testable surface; reuses `_rewrite` / position
  predicates; the refuse-on-doubt model bounds the blast radius.
- **Cons:** will refuse some legal-but-exotic designs (deep generate/hierarchical
  cases, macro-pasted instantiations) rather than handle them. Documented limitation.

### B — Adopt a real HDL parser dependency

Pull in a full grammar (e.g. tree-sitter-verilog/-vhdl, or hdlConvertor) and rewrite
from a parse tree.

- **Pros:** handles generate blocks, instance arrays, hierarchy, configs — the cases A
  refuses.
- **Cons:** a native/compiled runtime dependency and a large new subsystem; complicates
  the wheel/CI and the vendor-neutral story; HDL's preprocessor/config corners still
  bite; much larger review/test surface. pyslang is SV-only (no VHDL); hdlConvertor is
  heavyweight; tree-sitter grammars vary in fidelity.

**Recommendation: A.** The cores in scope are RTL *packages of IP*, not arbitrary
preprocessor-heavy code, and the classify-all-or-refuse model makes A *safe* even where
it is incomplete (it refuses, exactly as today). B is a project-character change we can
revisit later **if** real designs hit A's refusal boundary often — at which point this
doc's limitation list (§9) is the evidence to justify the dependency.

## 5. Position rules

### 5.1 SystemVerilog (modules / interfaces / programs)

**Declarations** (already scanned by `declared_modules`):
- `module <n>` / `macromodule <n>`, `interface <n>`, `program <n>`
- end labels: `endmodule : <n>`, `endinterface : <n>`, `endprogram : <n>`

**Instantiation** (modules, interfaces, programs) — rewrite a known name `<n>` when the
following significant tokens match the instantiation shape:

```
<n> [ #( ... ) ] <instance_name> [ [ ... ] ] (        // single or instance-array
<n> u1 ( ... ), u2 ( ... ) ;                           // multiple instances
```

i.e. `<n>` then an optional parameter map `#( … )`, then an *instance-name identifier*,
an optional packed/unpacked range, then `(`. This shape distinguishes an instantiation
from:
- a **function/task call** `n(...)` — no instance name between `n` and `(`;
- a **variable/net declaration** `t v;` — no `(`;
- a **hierarchical member** `top.n` — `<n>` is preceded by `.` (never rewritten).

**Interfaces have extra reference positions** (an interface name is also a *type*), all
of which must be mangled together with the declaration:
- as a **port/variable type**: `module m (my_if bus);` / `my_if bus;` — `<n>` followed
  by an identifier with **no** following `(` (distinguishes it from an instantiation and
  from a coincidental module-name-as-signal, which is illegal for a module but normal
  for an interface type);
- **virtual interface**: `virtual my_if vif;` — `<n>` preceded by `virtual`;
- **modport select**: `my_if.master m` / `my_if.slave` — `<n>` followed by `.` *and* a
  modport name (this is the one `.`-suffixed case we *do* rewrite, unlike a hierarchical
  member; disambiguated because `<n>` is a known interface name).

Programs are instantiation-only (like modules). Interface **type-parameter** defaults
(`#(type T = my_if)`) are an exotic reference we **refuse** (see §9), not rewrite.

**Generate is not special.** An instantiation nested in `generate` / `for` / `if` /
`case` produces the *same token shape* as one at module top level, and the rewriter
runs on the flat token stream, so these are matched with no scope tracking — e.g.
`for (genvar i=0;i<N;i++) begin : g  <n> u (...);  end`. Generate cases are covered by
the rule above and are exercised by the test plan (§10).

### 5.2 VHDL (entities) — case-insensitive

**Declarations** (scanned by `declared_vhdl_entities`, plus components):
- `entity <n> is`, `architecture <a> of <n> is`, `end entity <n>` / `end <n>`
- `component <n> [is]` … `end component <n>`
- `configuration <c> of <n> is`

**Instantiation** — two forms:
- **Direct** (unambiguous, like `use work.`): `<label> : entity work.<n>[(<arch>)]`
- **Component**: `<label> : [component] <n> [generic map|port map]`. Recognized as
  `<ident> :` followed by our known name `<n>` (which is *not* a statement keyword like
  `process`/`block`/`if`/`for`/`case`/`assert`), then `generic`/`port`/`;`/`component`.

Direct instantiation alone is feasible with today's machinery; component instantiation
needs the `<label> : <n> (generic|port)` shape recognizer above.

**Generate is not special** (same as SV): both the direct and component shapes appear
identically inside `for … generate` / `if … generate`, e.g.
`g: for i in 0 to N-1 generate  u: entity work.<n> port map (...);  end generate;`. The
flat-token rewriter matches them without scope tracking; covered by the test plan.

## 6. The safety model: classify-all-or-refuse

For each colliding unit name `n` that we intend to mangle, scan every source and
classify **every** significant occurrence of `n` as exactly one of:

- **declaration** — rewrite;
- **instantiation/reference** (per §5) — rewrite;
- **inert** — provably not a reference to the unit, left as-is. We classify inert
  **best-effort** (reviewer decision Q3 = "try also"), covering: comments/strings (the
  lexer already separates these); a hierarchical member `top.n` (preceded by `.`, and —
  for an interface — *not* followed by a modport name); a named-library ref
  `other_lib.n`; `n` as a plain **expression operand** or in a context where a unit name
  cannot legally appear (a module/entity is not a value, so `x = n`, `if (n)`, a port
  connection `.p(n)`, etc. cannot be a unit reference). For a **module/program** name,
  `n <ident> ;` (a would-be variable of module type) is illegal HDL, so we also treat a
  bare `n` not in instantiation shape as inert rather than refusing.
- **unclassifiable** — an occurrence that *could* be a reference but we cannot place
  with confidence (e.g. an interface name in an unmodeled type context, a macro-adjacent
  token).

If any occurrence is **unclassifiable**, raise `BackendError` and refuse the whole
coexistence for `n` (the current behavior). Only when *all* occurrences are
{declaration, instantiation/reference, inert} do we apply the rewrite. This guarantees
we never rename a declaration while leaving a real reference dangling, while the
best-effort inert classification keeps the refusal set small for normal RTL.

This is stricter than the package rewriter (which rewrites known positions and ignores
the rest) precisely because a unit's references are not keyword-marked, so "ignore the
rest" is unsafe. The collision safety net `_reject_colliding_mangled_names` (added in
0.11.0) still applies on top.

## 7. Architecture changes (all in `mangle.py` + CLI report)

- Generalize `plan_package_mangling` → `plan_mangling` handling a **unit kind**
  (`package` | `module`/`interface`/`program` | `entity`). Keep `plan_package_mangling`
  as a thin alias if anything imports it.
- New position predicates mirroring the package ones:
  `_is_sv_module_position` (decl + instantiation) and `_is_vhdl_entity_position`
  (decl + direct + component instantiation), driving the existing `_rewrite`.
- New `_classify_occurrences(...)` implementing §6; called before applying renames.
- `GenSourceFile`: extend `rewrite(...)` to also rewrite unit positions; reuse
  `declared_unit_names()` for the collision detection that today feeds the refusal.
- `_reject_unmangleable` shrinks: it no longer refuses *all* module/entity collisions —
  only the residual unhandleable cases (unknown language; macro-constructed names; a
  classify-all-or-refuse failure surfaces as its own `BackendError`).
- `_print_mangle_report` (CLI) extends to list mangled modules/entities; the
  `isolate_namespaces` warning text ("module/entity coexistence is still refused")
  updates to reflect the new support and the residual refusals.

No data-model change: `ManglePlan.renamed` already maps `name -> sorted mangled names`.

## 8. Format / CLI impact

None to `ip.toml` / `ip.lock` / the registry protocol / CLI flags. Behavior change is
limited to `gen` under `isolate_namespaces`: cases that previously errored now succeed
(when provably safe) or continue to error with a clearer message (when not).

## 9. Known limitations (what stays refused under A)

- Instantiations produced by **macro token-pasting** (`` `MK_INST(foo) ``) — the lexer
  cannot see inside macro bodies (same limitation as packages).
- **Interface type-parameter defaults** (`#(type T = my_if)`) and other unmodeled
  *type* contexts for an interface name → refused, not corrupted.
- A colliding name reached only through an **unmodeled construct** (an exotic `config` /
  `bind` corner) → refused, not corrupted.

**Explicitly supported (not limitations):** instantiations inside `generate` / `for` /
`if` / `case` blocks (both languages), SV instance arrays and `#(...)` param maps,
multiple instances per statement, SV interface ports / `virtual` / modport selects.

These refusals are the cases that, if hit by real designs, would justify revisiting
approach B.

## 10. Test plan

**Unit** (`tests/unit/test_mangle.py`):
- SV modules: instantiation rewrite (`n u(...)`, `n #(...) u(...)`, instance array
  `n u[..](...)`, multiple `n a(...), b(...)`), **inside a `generate`/`for`/`if` block**,
  endmodule label, leave `top.n` / comments / strings / expression operand `= n`,
  **refuse** an unclassifiable occurrence.
- SV interfaces: instantiation, **port type** `m(my_if bus)`, `virtual my_if v`,
  **modport select** `my_if.master`, leave a hierarchical `top.my_if`.
- VHDL: entity/architecture/end + component decl; direct `entity work.n` and component
  `lbl : n port map`, both **inside `… generate`**; case-insensitivity; leave
  `other_lib.n`; **refuse** unclassifiable.
- Planner: two module/entity/interface versions coexist → both mangled + every
  instantiation/reference routed to the version its core resolved to; collision safety
  net; refusal paths.

**Integration** (`tests/integration/`): `gen` over fixtures with two coexisting versions
of a module (SV, incl. a generate-nested instance), an interface (SV), and an entity
(VHDL); assert the materialized sources declare the mangled names and each consumer
references its own version.

**Real-toolchain proof** (a committed chunk, not a follow-up — reviewer decision Q4):
add a module-coexistence example (incl. a generate loop) to `hdlpkg-consumer-demo` and
build it through Verilator/GHDL in the `build` lane — a corrupt rewrite fails the
compile, the strongest possible check.

## 11. Phasing — small, independently reviewable commits (toward 0.12.0)

Each chunk is its own commit on `develop` carrying *code + tests + doc + tracker
update*, all gates green, no PR (per the workflow). Ordered so each is safe on its own:

1. **Planner core** — generalize `plan_package_mangling` → `plan_mangling` over a unit
   *kind*, add the `_classify_occurrences` safety scaffold. No behavior change yet:
   module/entity collisions still refuse, now via the new path.
2. **SV modules** (+ programs) — declaration + instantiation positions (incl. `#(...)`,
   instance arrays, multiple instances, **generate-nested**) + the inert classifier;
   lift the refusal for module-only collisions; unit tests.
3. **VHDL entities** — entity/architecture/component declarations + direct and component
   instantiation (incl. generate-nested); unit tests.
4. **SV interfaces** — the extra type/`virtual`/modport reference positions; unit tests.
5. **Integration + CLI report** — `gen` end-to-end fixtures; update the mangle report
   and the `isolate_namespaces` warning text.
6. **Demo proof** — module-coexistence example (with a generate loop) in
   `hdlpkg-consumer-demo`, built through Verilator/GHDL in the `build` lane.
7. **Docs close-out** — flip `architecture.md` / `INDEX.md` / this doc to
   "implemented"; move the tracker item to Completed.

The 0.12.0 release is cut (via `/release`) after the chunks land and the gates/CI and
the demo build lane are green.

## 12. Reviewer decisions (2026-06-15)

1. **Approach:** **A** (in-house, zero-dep) — chosen, for flexibility and the ability to
   grow the rewriter ourselves later.
2. **Scope:** include SV **interfaces** (and programs) alongside modules + VHDL entities.
   **Generate-nested instantiations are required** (both languages — very common in the
   target use cases) and are in scope from the start (§5).
3. **Refusal strictness:** **try to prove occurrences inert** (best-effort), refusing
   only genuinely ambiguous ones (§6) — not a blanket refuse on every bare identifier.
4. **Demo proof:** **add a committed example** to `hdlpkg-consumer-demo`'s build lane as
   part of this work (chunk 6), not a deferred pass.
