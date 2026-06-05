"""Core distribution: registries and the local cache (planned).

A *registry* is where packaged IP cores live so they can be discovered, fetched,
and published. A *cache* is the local, content-addressed store the packager
populates while resolving, so repeated builds are offline and reproducible.

Design intent (see ``docs/architecture.md`` and ``docs/research/state_of_the_art.md``):

* :class:`Registry` is an abstract interface so multiple backends can coexist:
  a local directory, a Git-backed channel, an HTTP index, or an **OCI artifact**
  registry (reusing Docker registry infrastructure for content-addressable,
  immutable storage).
* Artifacts are addressed by SHA-256 digest; the cache verifies the digest on
  every read so a tampered or corrupted core fails closed.
* Publishing is append-only/immutable; a bad release is *yanked* (hidden from new
  resolves) rather than deleted, preserving existing lockfiles.

This module exposes the intended interface only; bodies raise
:class:`NotImplementedError` until the milestone lands.
"""

from __future__ import annotations

import abc
from collections.abc import Iterable

from .vlnv import PackageRef, Vlnv

__all__ = ["Registry"]


class Registry(abc.ABC):
    """Abstract source/sink of packaged IP cores (one concrete backend per registry kind)."""

    @abc.abstractmethod
    def versions(self, ref: PackageRef) -> Iterable[Vlnv]:
        """Return every published version of *ref* (newest-first is not required)."""
        raise NotImplementedError

    @abc.abstractmethod
    def fetch(self, vlnv: Vlnv, dest: str) -> str:
        """Download *vlnv* into *dest*, verify its digest, and return the local path."""
        raise NotImplementedError

    @abc.abstractmethod
    def publish(self, artifact_path: str) -> Vlnv:
        """Publish a packaged ``.ipkg`` artifact; return the VLNV it was stored under."""
        raise NotImplementedError
