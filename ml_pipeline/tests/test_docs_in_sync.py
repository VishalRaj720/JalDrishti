"""The documented model metrics must match the deployed artifacts.

ARCHITECTURE.md Section 6.5 drifted from `metrics.json` across three separate
retrains. Each time the numbers were hand-copied, each time they were correct on
the day and wrong a commit later, and the third drift shipped a claim of
migration R2 = 0.896 against a deployed 0.535. This test makes that class of
failure impossible to merge.
"""
from __future__ import annotations

import json
import pytest

from ml_pipeline.tools.sync_docs import sync, ARCH, METRICS, BEGIN, END


def test_architecture_metrics_block_matches_the_artifacts():
    assert sync(check=True), (
        "ARCHITECTURE.md's generated metrics block is stale relative to "
        "ml/artifacts/metrics.json. Run:  python -m ml_pipeline.tools.sync_docs")


def test_generated_block_markers_are_present():
    text = ARCH.read_text(encoding="utf-8")
    assert BEGIN in text and END in text
    assert text.index(BEGIN) < text.index(END)


def test_no_hand_written_r2_claims_survive_outside_the_generated_block():
    """Guard against someone re-introducing a hand-typed metric next to the
    generated one -- which is exactly how the last drift happened."""
    text = ARCH.read_text(encoding="utf-8")
    outside = text.split(BEGIN)[0] + text.split(END, 1)[1]
    m = json.loads(METRICS.read_text())
    # any of the deployed R2 values appearing verbatim outside the block would
    # be a hand-copy waiting to go stale
    literals = set()
    for b in m["bands"].values():
        literals.add(f"{b['r2']['p50']:.3f}")
        literals.add(f"{b['r2_log']:.3f}")
    stale = [s for s in literals if s in outside]
    assert not stale, (
        f"metric literals {stale} appear in hand-written prose; move them into "
        f"the generated block so they cannot drift")
