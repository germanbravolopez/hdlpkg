# Errors — `exceptions.py`

One exception hierarchy rooted at a single base, so a caller (the CLI, or another
tool embedding the library) can catch the whole family with one `except`.

- **Source**: [src/hdl_ip_packager/exceptions.py](../../src/hdl_ip_packager/exceptions.py)
- **Import**: `from hdl_ip_packager import HdlPackagerError, ManifestError, ...`

## The hierarchy

```
HdlPackagerError                     (base — catch this to catch everything)
├── InvalidVersionError   (ValueError)   bad SemVer string
├── InvalidConstraintError(ValueError)   bad constraint grammar
├── InvalidVlnvError      (ValueError)   malformed vendor:library:name[:version]
├── ManifestError                        ip.toml missing/invalid data
├── ResolutionError                      constraints cannot be satisfied
├── LockfileError                        ip.lock malformed or integrity check failed
├── PackagingError                       building/extracting an .ipkg failed
├── RegistryError                        a registry/cache operation failed
└── BackendError                         a tool-flow backend could not generate inputs
```

The three `Invalid*` value-parsing errors also subclass `ValueError`, so code that
expects a `ValueError` from a parse still works.

## Conventions

- **Library code raises; it never prints.** Only the [CLI](cli.md) entry point
  formats errors for the user — it catches `HdlPackagerError`, prints
  `error: <message>` to stderr, and returns exit code 1.
- **Messages name the offending input** (the bad field, the unsatisfiable package,
  the mismatched checksum), so failures are actionable.
- New error types are added here, keeping the hierarchy in one place.

## Example

```python
from hdl_ip_packager import Manifest, HdlPackagerError, ManifestError

try:
    Manifest.from_str("not a manifest")
except ManifestError as exc:
    print("specific:", exc)
except HdlPackagerError as exc:
    print("any packager error:", exc)
```
