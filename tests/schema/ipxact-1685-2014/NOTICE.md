# Vendored schema: IEEE 1685-2014 IP-XACT (Accellera)

These `.xsd` files are the **official Accellera IP-XACT IEEE 1685-2014 schema set**,
vendored here **verbatim and unmodified** so the test suite can validate
`hdlpkg export-ipxact` output against the real standard (see
[`tests/unit/test_ipxact_xsd.py`](../../unit/test_ipxact_xsd.py)). They are **test
fixtures only** — not shipped in the `hdl-ip-packager` wheel and not imported by the
library at runtime.

- **Source**: <http://www.accellera.org/XMLSchema/IPXACT/1685-2014/> (entry point
  `index.xsd`, which `include`s the rest). Downloaded as the complete set; there are no
  external schema imports.
- **Copyright**: © 2005–2012 Accellera Systems Initiative Inc. All rights reserved.
- **License**: each file carries the full Accellera license in its header. It permits
  copying and **verbatim** redistribution provided the notice is kept and the files are
  **not modified, adapted, or altered**, and explicitly allows a tool to include full
  copies of the schema. This is independent of the project's own MIT license (which
  covers `hdlpkg`'s code, not these third-party files).

**Do not edit these files.** The license forbids modification, and editing would also
make them no longer the official schema we validate against. To refresh, re-download the
verbatim set from the URL above.
