# Vendored schema: IEEE 1685-2022 IP-XACT (Accellera)

These `.xsd` files are the **official Accellera IP-XACT IEEE 1685-2022 schema set**,
vendored here **verbatim and unmodified** so the test suite can validate
`hdlpkg export-ipxact --std 2022` output against the real standard (see
[`tests/unit/test_ipxact_xsd.py`](../../unit/test_ipxact_xsd.py)). They are **test
fixtures only** — not shipped in the `hdlpkg` wheel and not imported by the library at
runtime.

- **Source**: <https://www.accellera.org/XMLSchema/IPXACT/1685-2022/> (entry point
  `index.xsd`, which `include`s the rest). Downloaded as the complete set; the only
  external reference is the W3C `xml.xsd`, fetched alongside.
- **License**: unlike the 2014 set, the 2022 schema is distributed under the **Apache
  License, Version 2.0** (each file carries the Apache header; see also the upstream
  `NOTICE`). Apache-2.0 permits redistribution. This is independent of the project's own
  MIT license (which covers `hdlpkg`'s code, not these third-party files).

**Do not edit these files** — editing would make them no longer the official schema we
validate against. To refresh, re-download the verbatim set from the URL above.
