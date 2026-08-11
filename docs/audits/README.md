# Audit and remediation record

Chronological. Each audit found defects in the state left by the previous one, so
reading them in order is the only way to tell a live finding from a retracted one.
**Nothing here is merged or rewritten** — some findings were later proven wrong, and
the record of that mistake is the point.

| # | Document | Date | What it is |
|---|---|---|---|
| 1 | [`FABLE5_QA_SWEEP_PROMPT.md`](FABLE5_QA_SWEEP_PROMPT.md) | 2026-07 | The executable QA brief (§4A–§4E battery) run before the final retrain |
| 2 | [`QA_SWEEP_REPORT.md`](QA_SWEEP_REPORT.md) | 2026-07-13 | Its output: ~1,100 cases across 9 pins, findings F-1…F-5 |
| 3 | [`review.md`](review.md) | 2026-08 | Full architecture + hydrogeology audit; findings #1…#9 |
| 4 | [`REMEDIATION_PROMPT.md`](REMEDIATION_PROMPT.md) | 2026-08-05 | The brief for closing `review.md`, incl. the two-implementation `max_migration_distance_m` trap |
| 5 | [`REMEDIATION_GATE3_DECISION.md`](REMEDIATION_GATE3_DECISION.md) | 2026-08-05 | Pilot-bake review; the decision to proceed with `BETA_SORPTION_STRENGTH = 1.0` |
| 6 | [`review2.md`](review2.md) | 2026-08 | Second audit; findings V-1…V-8 |
| 7 | [`DOMENICO_ERROR_ENVELOPE.md`](DOMENICO_ERROR_ENVELOPE.md) | 2026-08-05 | Deliverable for V-1: the transport kernel measured against an exact solution |
| 8 | [`review3.md`](review3.md) | 2026-08-10 | Third audit; findings D-1…D-7 |
| 9 | [`ML_PIPELINE_READINESS.md`](ML_PIPELINE_READINESS.md) | 2026-08-10 | **Current state of truth.** Post-remediation readiness report; §7 lists the frozen limitations |

## Retractions worth knowing

- `QA_SWEEP_REPORT.md` "surprising-but-correct" item #3 certified a 422.8 m Jaduguda
  migration as Tang-envelope physics. It was grid geometry, not physics. Retracted by
  `review.md` finding #2 — a prior audit had blessed an artifact with a wrong mechanism.
- Read `ML_PIPELINE_READINESS.md` §7 before treating any older number here as current.
  The pipeline was re-baked and retrained during the `review3.md` remediation, so
  metrics quoted in documents 1–8 predate the deployed model.

Code comments across `ml_pipeline/` cite these by bare name (`review.md finding #2`,
`review2.md V-8`). Those are stable identifiers, not paths — they were left alone in
the reorganisation rather than churning ~60 source files.
