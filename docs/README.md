# JalDrishti documentation

Reorganised 2026-08-11. Everything that used to be scattered across the repo root,
`mdFiles/`, and `ml_pipeline/` now lives here — except four files that stay next to
the code because tooling loads them by path (see *Docs that deliberately stay put*).

## Where to start

| If you want to… | Read |
|---|---|
| Understand what the product is and how the three codebases join up | [`../PRODUCT_DESIGN.md`](../PRODUCT_DESIGN.md) |
| Understand the ISR plume surrogate end to end | [`../ml_pipeline/ARCHITECTURE.md`](../ml_pipeline/ARCHITECTURE.md) |
| Run the surrogate or retrain it | [`../ml_pipeline/README.md`](../ml_pipeline/README.md) |
| Know what is trustworthy and what is not | [`audits/ML_PIPELINE_READINESS.md`](audits/ML_PIPELINE_READINESS.md) |
| Know which role can reach which endpoint | [`roles.md`](roles.md) — generated from the running app |
| Check where a physical constant came from | [`../ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md`](../ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md) |
| Set up and run the whole repo | [`../README.md`](../README.md) |

## `audits/` — the review and remediation record (tracked)

The audit trail is kept intact rather than summarised: several findings were later
**retracted or corrected**, and collapsing the documents would erase which claim was
superseded by which. See [`audits/README.md`](audits/README.md) for the chronology.

## `local/` — not tracked in git

Learning write-ups, research dumps, and reference PDFs. Previously ignored as
`/mdFiles`, `datasets_source.md`, and `My_Proposal.pdf`; `.gitignore` now covers the
whole folder as `docs/local/`. Three of these describe code that no longer exists and
carry a staleness banner saying so.

## Docs that deliberately stay put

Moving these breaks the test suite, so they remain in `ml_pipeline/`:

| File | Loaded by |
|---|---|
| `ARCHITECTURE.md` | `tools/sync_docs.py` writes §6.5; `tests/test_docs_in_sync.py` fails the suite if it drifts |
| `README.md` | `validation/end_to_end_audit.py` (containment check) |
| `JHARKHAND_FIDELITY_MATRIX.md` | `validation/end_to_end_audit.py` (marker check) |
| `E1_geometry_design.md` | the design contract those two cite; kept alongside them |

`Datasets/**/*.md` also stay where they are — they are data provenance cited by
`ml_pipeline/config/parameters.py`, not documentation.
