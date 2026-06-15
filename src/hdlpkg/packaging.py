"""Packaging: build and read the distributable ``.ipkg`` artifact.

An ``.ipkg`` is the single-file form of an IP core used for distribution: a
gzip-compressed tar holding the core's ``ip.toml`` plus every file its filesets
declare. It is built **deterministically** -- entries sorted by name, fixed
mode/owner, zero mtime, and a zeroed gzip header -- so the same core always packs
to byte-identical bytes, which makes its SHA-256 a stable content address. This is
the artifact the registry serves, the cache stores, and the lockfile pins.

The module is the packaging layer's pure-ish core: it reads the declared files
from a core directory and returns bytes (`pack_core`), and unpacks bytes back to a
directory (`extract_ipkg`) with path-traversal protection. Errors raise
:class:`PackagingError`.
"""

from __future__ import annotations

import gzip
import io
import re
import tarfile
from collections.abc import Iterable
from pathlib import Path

from .exceptions import PackagingError
from .manifest import MANIFEST_FILENAME, Manifest
from .vlnv import Vlnv

__all__ = [
    "IPKG_SUFFIX",
    "artifact_filename",
    "expand_fileset_files",
    "extract_ipkg",
    "manifest_from_ipkg",
    "pack_core",
]

IPKG_SUFFIX = ".ipkg"

# A path that uses any of these is treated as a glob pattern rather than a literal file.
_GLOB_MAGIC = re.compile(r"[*?\[]")


def _reject_escape(fileset_name: str, pattern: str) -> None:
    """Reject a fileset path that would reach outside the core directory."""
    if pattern.startswith("/") or ".." in pattern.split("/") or Path(pattern).is_absolute():
        raise PackagingError(
            f"Fileset '{fileset_name}' path escapes the core directory: {pattern!r}"
        )


def expand_fileset_files(core_dir: Path, fileset_name: str, patterns: Iterable[str]) -> list[str]:
    """Expand a fileset's path patterns against *core_dir* into concrete relative paths.

    Each entry of a ``[filesets]`` ``files`` list may be:

    * a **literal** file path (kept as-is, so a missing file is still reported on read);
    * a **glob** -- any entry containing ``*``, ``?`` or ``[`` (``**`` recurses), expanded
      relative to *core_dir* and matching files only; or
    * an existing **directory**, expanded to every file under it, recursively.

    Author order is preserved across entries; matches *within* a glob or directory are
    sorted, and the whole list is de-duplicated (first occurrence wins) so packaging is
    deterministic. Paths that escape the core (absolute or containing ``..``) are rejected,
    and a glob or directory that matches no file is an error (a likely authoring mistake).
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(rel: str) -> None:
        if rel not in seen:
            seen.add(rel)
            out.append(rel)

    for raw in patterns:
        pattern = raw.replace("\\", "/")
        _reject_escape(fileset_name, pattern)
        if _GLOB_MAGIC.search(pattern):
            matches = sorted(p for p in core_dir.glob(pattern) if p.is_file())
            if not matches:
                raise PackagingError(f"Fileset '{fileset_name}' glob matched no files: {raw!r}")
            for match in matches:
                add(match.relative_to(core_dir).as_posix())
        elif (core_dir / pattern).is_dir():
            matches = sorted(p for p in (core_dir / pattern).rglob("*") if p.is_file())
            if not matches:
                raise PackagingError(f"Fileset '{fileset_name}' directory has no files: {raw!r}")
            for match in matches:
                add(match.relative_to(core_dir).as_posix())
        else:
            # A literal path: keep it so a typo still surfaces as a missing-file error.
            add(pattern)
    return out


def artifact_filename(vlnv: Vlnv) -> str:
    """The conventional ``.ipkg`` filename for *vlnv*."""
    return f"{vlnv.vendor}-{vlnv.library}-{vlnv.name}-{vlnv.version}{IPKG_SUFFIX}"


def _collect(manifest: Manifest, core_dir: Path) -> dict[str, bytes]:
    """Read the manifest + every fileset file into an ``{arcname: bytes}`` map."""
    files: dict[str, bytes] = {}
    manifest_path = core_dir / MANIFEST_FILENAME
    try:
        files[MANIFEST_FILENAME] = manifest_path.read_bytes()
    except OSError as exc:
        raise PackagingError(f"Cannot read {manifest_path}: {exc}") from exc
    for fileset in manifest.filesets.values():
        # Expand globs/directories to concrete files (and reject paths escaping the
        # core, which would also produce an .ipkg extract_ipkg later refuses to unpack).
        for arcname in expand_fileset_files(core_dir, fileset.name, fileset.files):
            try:
                files[arcname] = (core_dir / arcname).read_bytes()
            except OSError as exc:
                raise PackagingError(
                    f"Fileset '{fileset.name}' references missing file '{arcname}': {exc}"
                ) from exc
    return files


def pack_core(manifest: Manifest, core_dir: str | Path) -> bytes:
    """Pack the core at *core_dir* into deterministic ``.ipkg`` bytes."""
    core_dir = Path(core_dir)
    files = _collect(manifest, core_dir)
    raw = io.BytesIO()
    # mtime=0 zeroes the gzip header timestamp so output is reproducible.
    with (
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        for arcname in sorted(files):
            data = files[arcname]
            info = tarfile.TarInfo(arcname)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    return raw.getvalue()


def _open_ipkg(data: bytes) -> tarfile.TarFile:
    try:
        return tarfile.open(fileobj=gzip.GzipFile(fileobj=io.BytesIO(data)), mode="r")
    except (OSError, tarfile.TarError) as exc:
        raise PackagingError(f"Not a valid .ipkg archive: {exc}") from exc


def manifest_from_ipkg(data: bytes) -> Manifest:
    """Parse the ``ip.toml`` carried inside an ``.ipkg``."""
    with _open_ipkg(data) as tar:
        try:
            member = tar.extractfile(MANIFEST_FILENAME)
        except KeyError:
            member = None
        if member is None:
            raise PackagingError(f"Archive has no {MANIFEST_FILENAME}.")
        return Manifest.from_str(member.read().decode("utf-8"))


def extract_ipkg(data: bytes, dest: str | Path) -> Path:
    """Extract an ``.ipkg`` into *dest*, rejecting unsafe paths; return *dest*."""
    dest = Path(dest)
    with _open_ipkg(data) as tar:
        for member in tar.getmembers():
            member_path = Path(member.name)
            if member.name.startswith("/") or ".." in member_path.parts:
                raise PackagingError(f"Refusing unsafe path in archive: {member.name!r}")
            if not (member.isfile() or member.isdir()):
                raise PackagingError(f"Refusing non-regular archive member: {member.name!r}")
        dest.mkdir(parents=True, exist_ok=True)
        tar.extractall(dest)  # members validated above
    return dest
