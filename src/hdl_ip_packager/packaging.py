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
import tarfile
from pathlib import Path

from .exceptions import PackagingError
from .manifest import MANIFEST_FILENAME, Manifest
from .vlnv import Vlnv

__all__ = [
    "IPKG_SUFFIX",
    "artifact_filename",
    "extract_ipkg",
    "manifest_from_ipkg",
    "pack_core",
]

IPKG_SUFFIX = ".ipkg"


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
        for relative in fileset.files:
            arcname = relative.replace("\\", "/")
            # A fileset must stay inside the core: reject absolute paths and any
            # ``..`` that would pack a file from outside the core directory (which
            # would also produce an .ipkg extract_ipkg later refuses to unpack).
            if (
                arcname.startswith("/")
                or ".." in arcname.split("/")
                or Path(relative).is_absolute()
            ):
                raise PackagingError(
                    f"Fileset '{fileset.name}' path escapes the core directory: {relative!r}"
                )
            try:
                files[arcname] = (core_dir / relative).read_bytes()
            except OSError as exc:
                raise PackagingError(
                    f"Fileset '{fileset.name}' references missing file '{relative}': {exc}"
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
