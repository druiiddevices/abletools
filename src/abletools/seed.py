"""Seed normalization for reproducible generators."""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any


def derive_seed(seed: int, namespace: str, parameters: dict[str, Any] | None = None) -> int:
    """Derive a stable 64-bit child seed from user input and generator parameters."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    payload = {
        "namespace": namespace,
        "parameters": parameters or {},
        "seed": seed,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(encoded, digest_size=8).digest(), "big")


def seeded_rng(seed: int, namespace: str, parameters: dict[str, Any] | None = None) -> random.Random:
    """Return an isolated deterministic random-number generator."""
    return random.Random(derive_seed(seed, namespace, parameters))
