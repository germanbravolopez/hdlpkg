# State of the Art — IP & Package Managers

> Research survey backing the design of the HDL IP Packager.
> Compiled June 2026. Sources are listed at the bottom and linked inline.

This document answers one question: **what does a great package manager look like,
and how have people applied those ideas to HDL/IP?** It pulls from both the
mature software ecosystems (pip, npm, Cargo, Go, Conda, Docker/OCI) and the
hardware-specific tools (IP-XACT, FuseSoC, Bender, Orbit, hdlmake, vendor
catalogs). The conclusions feed directly into [architecture.md](../architecture.md).

---

## 1. The anatomy of a package manager

Across every ecosystem, the same handful of concepts recur. Naming them gives us
a checklist for our own design.

| Concept | What it is | Our choice |
|---------|-----------|------------|
| **Manifest** | Human-authored declaration of *what a project needs*: identity, metadata, direct dependencies with version constraints. | `ip.toml` (TOML) |
| **Lockfile** | Machine-generated record of *what was actually resolved* — exact versions + integrity hashes — for reproducible builds. | `ip.lock` (implemented) |
| **Resolver** | Turns constraints into concrete versions. | newest-compatible, SAT-ready (implemented) |
| **Registry** | Where packages are published and discovered. | local + HTTP (implemented); Git / OCI (planned) |
| **Cache** | Local, verified copy of fetched packages so builds are offline & reproducible. | content-addressed (implemented) |
| **Versioning** | The contract for "what changed". | SemVer 2.0.0 |
| **Identity** | A globally meaningful name. | VLNV (IP-XACT-style) |

The manifest declares constraints; the resolver finds concrete versions that
satisfy them; the lockfile records the result. This **manifest → resolve → lock**
loop is the spine of pip, npm, Cargo, Poetry, Go, and Bundler alike
([Nesbitt, *Package Manager Glossary*](https://nesbitt.io/2026/01/13/package-manager-glossary.html)).

---

## 2. Lessons from software package managers

### Versioning and constraints
- **Semantic Versioning** (`MAJOR.MINOR.PATCH`) is the near-universal contract:
  a major bump signals a breaking change. Constraint syntaxes converge on
  `>=1.0.0`, `^1.0.0` ("compatible with"), `~1.0.0` ("approximately"), and exact
  pins, though the **caret/tilde meaning differs per ecosystem** — npm and Cargo
  agree that `^` means "minor+patch for 1.x, patch only for 0.x"
  ([Nesbitt, *Glossary*](https://nesbitt.io/2026/01/13/package-manager-glossary.html)).
  → We implement SemVer 2.0.0 and adopt the **Cargo/npm caret semantics**, with a
  bare constraint defaulting to caret.

### Dependency resolution
- **Version selection is NP-complete** (you can encode 3-SAT into a dependency
  graph), which is why mature managers ship **SAT solvers** (e.g. Conda's
  `libmamba`, PubGrub in Dart/uv).
- Strategy differs: most pick the **newest** version satisfying constraints; **Go
  modules** use *Minimal Version Selection* (the oldest that works) for
  reproducibility without a lockfile
  ([Nesbitt, *Design Tradeoffs*](https://nesbitt.io/2025/12/05/package-manager-tradeoffs.html)).
- Conflict handling is a defining tradeoff: **pip fails** on incompatible
  versions; **npm nests** conflicting copies so each consumer gets what it asked
  for. HDL **cannot nest** — two copies of the same module in one elaboration
  collide — so we must resolve to a **single version per package** (pip-like), and
  fail loudly on conflict.

### Lockfiles & reproducibility
- Cargo set the modern convention: **lockfile by default, SemVer enforced,
  reproducible builds as a goal**. A study across npm/pnpm/Cargo/Poetry/Pipenv/
  Gradle/Go found lockfiles deliver *build determinism, integrity verification,
  and transparency*; commit rates vary wildly (Go ~100%, Gradle ~0%)
  ([Wang et al., *The Design Space of Lockfiles*](https://arxiv.org/pdf/2505.04834)).
  → We will commit `ip.lock` and store an integrity hash per resolved core.

### Publishing & trust
- **Immutability + yank**: Cargo and RubyGems never delete a published version;
  they *yank* it (hidden from new resolves, still available to existing
  lockfiles). This preserves reproducibility while letting you retire a bad
  release ([Nesbitt, *Glossary*](https://nesbitt.io/2026/01/13/package-manager-glossary.html)).
  → Our registry contract is append-only with yank.

### Registries & content-addressable storage
- An **OCI registry** (the Docker registry, now an open standard) is a
  *content-addressable, HTTP artifact store* where every blob is addressed by its
  **SHA-256 digest**, giving automatic dedup and integrity. Since the OCI 1.1
  specs (2024), registries store *any* artifact — Helm charts, WASM, ML models,
  Terraform modules — not just container images
  ([Chainguard, *What are OCI Artifacts*](https://edu.chainguard.dev/open-source/oci/what-are-oci-artifacts/);
  [ORAS](https://oras.land/docs/concepts/artifact/)).
  → A compelling backend option: **publish IP cores as OCI artifacts** and reuse
  the world's existing registry infrastructure (GHCR, ECR, Harbor) instead of
  inventing a new server. Content-addressing also underpins our local cache.

### Supply-chain security (the 2026 baseline)
- Driven by EO 14028 and the EU Cyber Resilience Act, three technologies have
  gone from buzzword to requirement: **SBOM** (what's inside), **SLSA** (build
  provenance levels L1–L3), and **Sigstore** (keyless signing via cosign/Fulcio/
  Rekor). SBOMs should be generated **at build time** when the full dependency
  graph is known ([AquilaX, *Beyond SBOMs*](https://aquilax.ai/blog/supply-chain-artifact-signing-slsa);
  [Practical DevSecOps, *SLSA Guide*](https://www.practical-devsecops.com/slsa-framework-guide-software-supply-chain-security/)).
  → Roadmap: checksums first, then optional Sigstore signing + an SBOM emitted by
  `pack`.

---

## 3. HDL-specific prior art

Hardware reuse has its own decades-long history. The key players:

### IP-XACT / IEEE 1685 — the metadata standard
The XML standard (IEEE 1685, originally from the SPIRIT Consortium; revisions
2009/2014/2022) for describing and packaging IP: components, bus interfaces,
address maps, register/field descriptions, and file sets, so tools and
organizations can exchange IP and automate integration. It standardizes the
**VLNV** (Vendor-Library-Name-Version) identity we adopt
([IP-XACT, Wikipedia](https://en.wikipedia.org/wiki/IP-XACT);
[IEEE 1685-2022](https://standards.ieee.org/ieee/1685/10583/)).
→ IP-XACT is a *description* format, not a package manager. We borrow its VLNV
identity and will offer **IP-XACT export** for tool interop, but use TOML (not
XML) for the human-authored manifest.

### FuseSoC — the de-facto open-source HDL package manager
Award-winning Python tool by Olof Kindgren. The unit is a **core** identified by
a **VLNV** (e.g. `example:ip:fifo`), described by a `.core` file (CAPI2, YAML)
listing sources and dependencies. The **package manager** searches configurable
**core libraries** (local dirs or remote repos); the **build system** resolves
the dependency tree from a top-level core, influenced by **constraints** (target,
tool, parameters), and flattens to a file list. It abstracts EDA tools via **tool
flows** and emits **EDAM** (an intermediate description) consumed by *Edalize*;
**generators** produce cores dynamically
([FuseSoC docs](https://fusesoc.readthedocs.io/en/stable/user/overview.html);
[GitHub](https://github.com/olofk/fusesoc)).
→ The closest reference design. We adopt VLNV, core libraries (local + remote),
constraint-influenced resolution, and an EDAM-like tool-abstraction layer.

### Bender — Git-first dependency manager (PULP, Rust)
Manages HDL package dependencies across **Git repositories and local paths**,
resolves compatible versions, records the exact result in **`Bender.lock`**, and
emits ordered source sets for downstream tools. Manifest (`Bender.yml`) is YAML;
ships as a single static binary
([Bender, GitHub](https://github.com/pulp-platform/bender)).
→ Validates the manifest+lockfile+ordered-filelist model and Git-as-registry.

### Orbit — modern, reproducibility-focused (Rust)
Package manager + build system for VHDL/Verilog/SystemVerilog. Manifest is
**`Orbit.toml`**; it **tokenizes HDL source** to find references between design
units automatically. A 3-level **Catalog** (Channels → Archive → Cache) stores
increasing detail; **checksums** lock cache contents so they can't be edited, and
an **`Orbit.lock`** captures the full state for cross-machine reproducibility
([Orbit Book](https://chaseruskin.github.io/orbit/topic/overview.html);
[GitHub](https://github.com/chaseruskin/orbit)).
→ Strong endorsement of our choices: **TOML manifest, lockfile, and
checksum-verified content-addressed cache**. The catalog tiering is a good model.

### hdlmake — the older Makefile generator
Python tool (CERN/Ohwr): finds file dependencies, writes synthesis/simulation
**Makefiles**, and fetches IP-core libraries from remote repos. Each module has a
`Manifest.py` (Python) listing files + dependencies
([Awesome HDL / hdlmake](https://hdl.github.io/awesome/items/hdlmake/)).
→ Shows the pitfall to avoid: a manifest in a *Turing-complete* language (`.py`)
is hard to analyze, sandbox, and trust. We keep the manifest **declarative (TOML)**.

### Vendor tooling — Vivado IP Packager / IP Integrator
AMD/Xilinx **IP Packager** prepares IP for the **IP Catalog**, leveraging
**IP-XACT**; **IP Integrator** connects IP at the block level (interface-based
connections, automation, DRCs) and generates RTL. The flow guarantees a
consistent experience whether IP is from the vendor, a third party, or custom
([UG896 IP Packager](https://docs.amd.com/r/en-US/ug896-vivado-ip/IP-Packager)).
→ Confirms IP-XACT as the interop lingua franca and the value of a **catalog**
abstraction. Our IP-XACT export targets exactly this consumer.

---

## 4. Comparison at a glance

| Tool | Manifest | Lockfile | Identity | Registry | Notable idea |
|------|----------|----------|----------|----------|--------------|
| pip / PyPI | `pyproject.toml` | (via pip-tools/uv) | name+version | PyPI index | huge ecosystem, fails on conflict |
| npm | `package.json` | `package-lock.json` | name+semver | npm registry | nested deps |
| Cargo | `Cargo.toml` | `Cargo.lock` | name+semver | crates.io | lockfile-by-default, yank |
| Go | `go.mod` | `go.sum` | module path | proxy/VCS | minimal version selection |
| Docker/OCI | (Dockerfile) | digest pin | repo:tag@digest | OCI registry | content-addressable artifacts |
| **IP-XACT** | XML | — | **VLNV** | — | the metadata standard |
| **FuseSoC** | `.core` (YAML) | — | **VLNV** | core libraries | tool-flow abstraction (EDAM) |
| **Bender** | `Bender.yml` | `Bender.lock` | name+semver | Git | Git-first |
| **Orbit** | `Orbit.toml` | `Orbit.lock` | name+version | Catalog | checksummed cache, source tokenizing |
| **This project** | `ip.toml` (TOML) | `ip.lock` | **VLNV** | local/Git/HTTP/**OCI** | TOML + SemVer + OCI backend + IP-XACT export |

---

## 5. Design decisions this research drives

1. **TOML manifest (`ip.toml`)** — declarative (not Python like hdlmake), modern,
   and the same family as Cargo/Orbit/`pyproject.toml`. *(implemented)*
2. **VLNV identity** — align with IP-XACT/FuseSoC so names are portable. *(implemented)*
3. **SemVer 2.0.0 + caret-default constraints** — the dominant library convention. *(implemented)*
4. **Single-version resolution, fail-on-conflict** — HDL can't nest; mirror pip,
   not npm. Newest-compatible selection, SAT-ready. *(implemented)*
5. **Committed lockfile + per-core integrity hash** — reproducibility like Cargo/
   Orbit/Go. *(implemented)*
6. **Content-addressed cache + pluggable registries, including an OCI backend** —
   reuse battle-tested infrastructure rather than build a server.
   *(cache + local/HTTP registries implemented; Git/OCI backends planned)*
7. **Tool-flow abstraction (EDAM-like)** — generate simulator/synthesis inputs
   from one description, à la FuseSoC. *(implemented — Verilator/Vivado/Icarus/GHDL/Yosys)*
8. **IP-XACT export** — interop with Vivado and other IEEE-1685 consumers. *(implemented)*
9. **Supply-chain on the roadmap** — checksums now; Sigstore signing + SBOM later.
   *(checksums + CycloneDX SBOM implemented; Sigstore signing planned)*

---

## Sources

HDL / IP:
- [FuseSoC — Understanding FuseSoC (docs)](https://fusesoc.readthedocs.io/en/stable/user/overview.html) · [FuseSoC GitHub](https://github.com/olofk/fusesoc)
- [IP-XACT — Wikipedia](https://en.wikipedia.org/wiki/IP-XACT) · [IEEE 1685-2022](https://standards.ieee.org/ieee/1685/10583/)
- [Bender — GitHub](https://github.com/pulp-platform/bender)
- [Orbit — The Orbit Book](https://chaseruskin.github.io/orbit/topic/overview.html) · [Orbit GitHub](https://github.com/chaseruskin/orbit)
- [hdlmake — Awesome HDL](https://hdl.github.io/awesome/items/hdlmake/) · [Build systems for HDL — Sigasi](https://www.sigasi.com/tech/build-systems-for-hdl/)
- [Vivado IP Packager — UG896](https://docs.amd.com/r/en-US/ug896-vivado-ip/IP-Packager)

Software package managers & registries:
- [Nesbitt — Package Manager Glossary](https://nesbitt.io/2026/01/13/package-manager-glossary.html)
- [Nesbitt — Package Manager Design Tradeoffs](https://nesbitt.io/2025/12/05/package-manager-tradeoffs.html)
- [Nesbitt — What Package Registries Could Borrow from OCI](https://nesbitt.io/2026/02/18/what-package-registries-could-borrow-from-oci.html)
- [Wang et al. — The Design Space of Lockfiles Across Package Managers (arXiv)](https://arxiv.org/pdf/2505.04834)
- [Chainguard — What are OCI Artifacts](https://edu.chainguard.dev/open-source/oci/what-are-oci-artifacts/) · [ORAS — OCI Artifact](https://oras.land/docs/concepts/artifact/)

Supply-chain security:
- [AquilaX — Supply Chain Security Beyond SBOMs](https://aquilax.ai/blog/supply-chain-artifact-signing-slsa)
- [Practical DevSecOps — SLSA Framework Guide 2026](https://www.practical-devsecops.com/slsa-framework-guide-software-supply-chain-security/)

Python packaging:
- [KDnuggets — Python Project Setup 2026 (uv + Ruff + Ty)](https://www.kdnuggets.com/python-project-setup-2026-uv-ruff-ty-polars)
- [Python Packaging Best Practices: setuptools, Poetry, Hatch in 2026](https://dasroot.net/posts/2026/01/python-packaging-best-practices-setuptools-poetry-hatch/)
