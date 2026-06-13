#!/usr/bin/env python3
"""Generate the ``hdlpkg(1)`` man page from the live CLI parser.

The command/option reference is *introspected* from ``cli.build_parser()`` so it can
never drift from the real CLI: every subcommand and flag in the man page is exactly
the one ``hdlpkg --help`` exposes. The narrative sections (description, the typical
producer/consumer workflow, files, registries, examples) are curated prose held in
this script.

The output is groff ``man(7)`` source. The committed copy lives at ``man/hdlpkg.1``;
regenerate it with this script whenever the CLI changes::

    python scripts/gen_manpage.py                 # write man/hdlpkg.1
    python scripts/gen_manpage.py --check         # fail if the committed page is stale
    python scripts/gen_manpage.py -o -            # write to stdout

View it without installing::

    man ./man/hdlpkg.1

Pure standard library + the packager itself; deterministic output (no timestamps), so
``--check`` is a reliable CI gate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Importable both as ``scripts/gen_manpage.py`` and via the installed package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hdl_ip_packager import __version__, cli

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "man" / "hdlpkg.1"


# --------------------------------------------------------------------------- escaping
def esc(text: str) -> str:
    """Escape text for a groff body line (backslashes; guard a leading control char)."""
    out = text.replace("\\", "\\e")
    if out[:1] in (".", "'"):
        out = "\\&" + out
    return out


def mono(text: str) -> str:
    """Escape text meant to read as literal/monospace (also protect the minus sign)."""
    return esc(text).replace("-", "\\-")


# --------------------------------------------------------------------------- options
def _is_flag(action: argparse.Action) -> bool:
    """True for a value-less switch (store_true / store_const)."""
    return action.nargs == 0


def _option_label(action: argparse.Action) -> str:
    """The bold tag for an option or positional, e.g. ``\\-o, \\-\\-output OUTPUT``."""
    if action.option_strings:
        meta = "" if _is_flag(action) else f" {action.metavar or action.dest.upper()}"
        label = ", ".join(mono(s) for s in action.option_strings) + mono(meta)
    else:  # positional
        name = action.metavar or action.dest
        label = mono(name if action.nargs not in ("?", "*") else f"[{name}]")
    if getattr(action, "required", False):
        label += "  (required)"
    return label


def _render_command(name: str, parser: argparse.ArgumentParser, help_text: str) -> list[str]:
    # .ad l per subsection: .SS resets adjustment to justified, which stretches the
    # spaces in a wrapped synopsis; ragged-right keeps commands readable.
    lines = [f".SS {esc(name)}", ".ad l"]
    if help_text:
        lines.append(esc(help_text[0].upper() + help_text[1:]) + ".")
    usage = " ".join(parser.format_usage().replace("usage:", "", 1).split())
    # Filled (not .EX) so a long synopsis wraps at the margin instead of overflowing.
    lines += [".PP", ".RS 4", mono(usage), ".RE"]
    actions = [a for a in parser._actions if a.dest != "help"]
    if actions:
        lines.append(".PP")
        for action in actions:
            help_ = (action.help or "").strip()
            lines += [".TP", ".B " + _option_label(action), esc(help_) if help_ else "\\ "]
    return lines


# --------------------------------------------------------------------------- prose
DESCRIPTION = r"""\fBhdlpkg\fR packages, versions, resolves, and distributes HDL IP cores
(Verilog, VHDL, SystemVerilog) \[em] a dependency manager for reusable hardware design
blocks, in the spirit of Cargo or npm but built for hardware realities.
.PP
A core is described once in a small, declarative \fBip.toml\fR manifest: its identity
(a \fBVLNV\fR \[em] vendor:library:name:version), its dependencies as version
\fIconstraints\fR, its source \fIfilesets\fR, and its build \fItargets\fR. From that,
\fBhdlpkg\fR resolves the full dependency graph to exact versions recorded in a
committed \fBip.lock\fR, fetches and integrity-verifies cores into a content-addressed
cache, packages a core into a deterministic \fB.ipkg\fR artifact for distribution over a
registry, and generates ready-to-run inputs for a simulator or synthesis tool.
.PP
\fBhdlpkg\fR does not replace your build flow: \fB[targets]\fR and \fBgen\fR are
optional, so a team with its own Makefile/Tcl flow can adopt \fBhdlpkg\fR purely to
version, verify, and distribute IP while keeping its existing tooling."""

WORKFLOW = r""".SS Producer \[em] publish a core
.EX
hdlpkg init \-\-vendor acme \-\-library comm \-\-name uart
hdlpkg validate ip.toml
hdlpkg pack ip.toml \-\-sbom
hdlpkg login   oci://harbor.corp/ip
hdlpkg publish ip.toml \-\-registry oci://harbor.corp/ip
.EE
.SS Consumer \[em] depend on it, reproducibly
.EX
hdlpkg add acme:comm:uart@^1.2.0
hdlpkg resolve ip.toml \-\-registry oci://harbor.corp/ip
hdlpkg install ip.toml \-\-registry oci://harbor.corp/ip \-\-locked
hdlpkg gen sim ip.toml \-\-locked \-\-output build/sim
.EE
.PP
\fBresolve\fR turns the version \fIconstraint\fR you declared into one exact,
conflict-free version of every core in the transitive graph and records it (plus a
SHA\-256 per core) in \fBip.lock\fR \[em] commit that file. \fBinstall \-\-locked\fR then
re-creates that exact set anywhere, verifying each fetched artifact against the lock and
failing closed on any mismatch; this is the reproducible / CI path. By contrast
\fBpull\fR is a one-off fetch of a single core by exact VLNV \[em] handy to inspect a
block, but it does not resolve a graph, pin versions, or give reproducibility."""

FILES = r""".TP
.B ip.toml
The core manifest at a project root: identity, dependencies, filesets, targets.
.TP
.B ip.lock
The generated, committed lockfile pinning every (transitive) dependency to one exact
version plus a SHA\-256 checksum. Commit it for reproducible builds.
.TP
.B ~/.hdlpkg/cache
Content-addressed cache of fetched cores, verified on every read.
.TP
.B ~/.hdlpkg/credentials.toml
Per-host registry tokens stored by \fBlogin\fR. A \fBdocker login\fR
(\fB~/.docker/config.json\fR) is reused as a fallback."""

REGISTRIES = r"""A \fB\-\-registry\fR / \fBlogin\fR \fILOCATION\fR is chosen by its scheme:
.TP
.B a path, e.g. ./registry
A local-directory registry (zero setup; a shared folder works).
.TP
.B http(s)://host/prefix
An HTTP registry (any GET/PUT-capable server).
.TP
.B oci://host/prefix
An OCI registry (JFrog Artifactory, Harbor, Nexus, GitLab, ECR/ACR, Zot); use
\fBoci+http://\fR for a plaintext/dev one.
.PP
Network registries are private by default: authenticate once with \fBhdlpkg login\fR
(a direct bearer token, or \fB\-\-username\fR for the OCI token-exchange). Publishing is
append-only \[em] a version is immutable; retire a bad one with \fByank\fR."""

VERSIONING = r"""A core's \fB[package].scheme\fR selects how its version string is interpreted:
.TP
.B semver
(default) Full SemVer 2.0.0 precedence and caret/tilde/range constraints.
.TP
.B calver
Ordered calendar versions (\fB2026.1\fR); the first component (year) is the
compatibility boundary.
.TP
.B monotonic
A single ordered revision stream (\fBr3\fR, \fBD5020204\fR); newest supersedes.
.TP
.B opaque
An uninterpreted vendor token, carried verbatim and pinned exactly.
.PP
Compatible dependents unify to one newest version (Cargo-style). A genuinely
incompatible conflict is handled by the \fB[resolution] on-conflict\fR policy
(\fB\-\-on\-conflict\fR): \fBfail_on_conflict\fR (default), \fBuse_latest\fR, or
\fBisolate_namespaces\fR (which name-mangles coexisting SystemVerilog/VHDL packages so
two versions can elaborate together)."""

EXAMPLES = r""".TP
.B Scaffold and check a new core
.EX
hdlpkg init \-\-vendor you \-\-library demo \-\-name widget
hdlpkg validate ip.toml
.EE
.TP
.B A non-SemVer vendor version
.EX
hdlpkg init \-\-vendor you \-\-library demo \-\-name widget \\
    \-\-version D5020204 \-\-scheme opaque
.EE
.TP
.B Inspect the resolved graph
.EX
hdlpkg tree ip.toml \-\-registry oci://harbor.corp/ip
.EE
.TP
.B Reproducible CI build (no re-resolve)
.EX
hdlpkg install ip.toml \-\-locked
hdlpkg gen sim ip.toml \-\-locked \-\-output build/sim
.EE
.TP
.B Grab one core to inspect it
.EX
hdlpkg pull acme:common:fifo:1.0.0 \-\-registry ./registry \-\-output ./fifo
.EE"""


# --------------------------------------------------------------------------- assembly
def render_manpage(version: str = __version__) -> str:
    parser = cli.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    helps = {c.dest: (c.help or "") for c in sub._choices_actions}

    out: list[str] = []
    # An empty date keeps the output deterministic (the version field carries the cut).
    out.append(f'.TH HDLPKG 1 "" "hdlpkg {esc(version)}" "HDL IP Packager Manual"')
    out += [".nh", ".ad l"]  # no hyphenation, left-adjust: kinder to commands/paths

    out += [".SH NAME", "hdlpkg \\- package, version, resolve, and distribute HDL IP cores"]

    out += [
        ".SH SYNOPSIS",
        ".B hdlpkg",
        r"[\fB\-\-version\fR] [\fB\-h\fR]",
        r".I command",
        r"[\fIargs\fR ...]",
    ]

    out += [".SH DESCRIPTION", DESCRIPTION]

    out.append(".SH COMMANDS")
    for name, subparser in sub.choices.items():
        out += _render_command(name, subparser, helps.get(name, ""))

    out += [".SH TYPICAL WORKFLOW", WORKFLOW]
    out += [".SH VERSIONING AND CONFLICTS", VERSIONING]
    out += [".SH REGISTRIES", REGISTRIES]
    out += [".SH FILES", FILES]
    out += [".SH EXAMPLES", EXAMPLES]

    out += [
        ".SH EXIT STATUS",
        "Returns \\fB0\\fR on success and \\fB1\\fR on any error (a bad manifest, an "
        "unresolvable graph, a registry/auth failure, or a checksum mismatch); the "
        "cause is printed to standard error.",
    ]

    out += [
        ".SH ENVIRONMENT",
        ".TP",
        ".B HOME",
        "Base for the default cache and credentials store (\\fB~/.hdlpkg\\fR).",
    ]

    out += [
        ".SH SEE ALSO",
        "Full documentation: \\fBhttps://germanbravolopez.github.io/hdl\\-ip\\-packager/\\fR",
        ".br",
        "Per-command help: \\fBhdlpkg \\fR\\fIcommand\\fR\\fB \\-\\-help\\fR",
    ]

    out += [".SH AUTHOR", "German Bravo Lopez."]
    out += [
        ".SH COPYRIGHT",
        "MIT License. This is free software: you are free to change and redistribute it.",
    ]

    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the hdlpkg(1) man page.")
    ap.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="output path, or '-' for stdout (default: man/hdlpkg.1)",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed page differs from a fresh render",
    )
    args = ap.parse_args(argv)

    page = render_manpage()

    if args.check:
        # newline="" keeps line endings untranslated so the comparison is byte-faithful.
        out = Path(args.output)
        existing = out.open(encoding="utf-8", newline="").read() if out.exists() else ""
        if existing != page:
            print(
                f"error: {args.output} is stale; run 'python scripts/gen_manpage.py'.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {args.output} is up to date.")
        return 0

    if args.output == "-":
        sys.stdout.write(page)
        return 0
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Always LF: a man page with CRLF triggers "invalid input character code 13".
    out_path.write_text(page, encoding="utf-8", newline="\n")
    print(f"wrote {out_path} ({page.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
