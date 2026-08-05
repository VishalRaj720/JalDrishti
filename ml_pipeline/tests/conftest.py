"""Shared pytest fixtures.

STATE ISOLATION (added 2026-08-05, independent-validation audit).
`ml_pipeline.config.parameters` is a plain module of module-level globals, so a
test that flips one mutates PROCESS-WIDE state that every later test inherits.
This was not hypothetical: tests in test_physics_laws.py toggled `E1_ENABLED`
and reset it to a hard-coded `False` in their `finally` blocks -- under a comment
reading "never leak the flag to other tests" -- while the PRODUCTION default is
`True`. Every test that happened to run afterwards was therefore validating
geometry the tool never serves, with the leach-zone disc switched off.

It surfaced as a genuine order-dependency: test_spatial_seams passed on its own
and failed in the full suite. Two tests were affected at the time of discovery;
the number that were silently weakened rather than failed is unknowable, which
is exactly why this is a fixture and not a per-test patch.

The fixture snapshots every tunable in the config module before each test and
restores it after, so no test can leak configuration into another regardless of
ordering, and `-p no:randomly` is not needed to get reproducible results.
"""
from __future__ import annotations

import pytest

from ml_pipeline.config import parameters as P

# Module-level names that are plain tunables (not functions, classes, imports).
_TUNABLES = [
    n for n, v in vars(P).items()
    if not n.startswith("__")
    and isinstance(v, (bool, int, float, str, tuple, frozenset))
]


@pytest.fixture(autouse=True)
def _restore_config_globals():
    """Snapshot/restore every config tunable around each test."""
    saved = {n: getattr(P, n) for n in _TUNABLES}
    # dict/list tunables are mutable -- copy them shallowly too
    mutable = {n: v for n, v in vars(P).items()
               if not n.startswith("__") and isinstance(v, (dict, list))}
    saved_mutable = {n: (v.copy() if hasattr(v, "copy") else v)
                     for n, v in mutable.items()}
    try:
        yield
    finally:
        for n, v in saved.items():
            setattr(P, n, v)
        for n, v in saved_mutable.items():
            setattr(P, n, v)
