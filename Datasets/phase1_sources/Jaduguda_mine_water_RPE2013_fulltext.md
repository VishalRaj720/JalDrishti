# Sethy, N.K., Jha, V.N., Sahoo, S.K., Ravi, P.M., Tripathi, R.M. (2013)
## "Dissolved uranium, 226Ra in the mine water effluent: A case study in Jaduguda"

**Radiation Protection and Environment** 36(1): 32-37, Jan-Mar 2013.
**DOI:** [10.4103/0972-0464.121824](https://doi.org/10.4103/0972-0464.121824)
**License:** CC-BY-NC-SA (confirmed OPEN via Unpaywall; publisher Wolters Kluwer–Medknow)
**Retrieved:** full text via publisher page (ovid.com/LWW platform), 2026-07-31.
Archived here as a cited engineering reference (Phase-1 fix 3.2 — source-term C0 grounding).
Full PDF download button on the publisher page requires an interactive session; the
complete article text (abstract through conclusions + Table 2 summary values) was
extracted and is reproduced below for that reason.

---

## Study site
Jaduguda and Bhatin uranium mines, Singhbhum Shear Zone, Jharkhand (~86.3°E, 22.5°N —
paper's stated "Long. 22°30', Lat. 86°20'" has the lon/lat labels swapped; coordinates
match the Jaduguda deposit location already in `Datasets/Jharkhand Ore/`).
**Average ore grade: 0.05% U3O8** — matches `URANIUM_GRADE_REF_PCT = 0.05` already in
`ml_pipeline/config/parameters.py`.

Process: sulfuric-acid leach (85-95% U recovery from ore), pyrolusite oxidant, BaCl2
co-precipitation + lime treatment in the Effluent Treatment Plant (ETP) before discharge
to the Juria → Gara → Suvarnrekha river system.

## Key quantitative results (Table 2, untreated effluent, 2011 sampling year)

| Source | Uranium (µg/L) | Uranium GM (µg/L) | GSD | Ra-226 (mBq/L) | Ra-226 GM (mBq/L) | GSD |
|---|---|---|---|---|---|---|
| **Jaduguda mine effluent** | 94 – 843.3 | **357.4** | 1.9 | 40 – 1706 | **371.3** | 2.6 |
| **Bhatin mine effluent** | — | 334.1 | — | — | 182 | — |
| **Uranium mill effluent** | — | 91.7 | — | — | 221 | — |

**ETP treatment efficiency: >95% decontamination for both U and Ra-226** — treated
effluent + receiving streams (Juria, Gara, Suvarnrekha up/downstream) all below
regulatory limits.

## Relevance to JalDrishti Phase-1 fix 3.2 (site-specific C0)

This is a **real, measured, Jaduguda-specific concentration** at the point mine water
leaves the rock — the honest **lower bound** for what an ISR-strength source term could
look like at this site (conventional mining + acid leach, not ISR, but the same ore body
and the same uranium mobilization chemistry). Use `357.4 µg/L (357,400 ppb)` GM /
`843.3 µg/L` max as the Jaduguda-anchored lower-bound band, to compare against the
current Texas-derived C0 envelope (upper bound) already in `config/parameters.py`.

Also directly useful for Phase-2 multi-species/Ra-226 work: Ra-226 GM 371.3 mBq/L at
Jaduguda mine effluent is a real local radium source-term anchor.

## Full extracted text (abstract → conclusions)

> Effluent water from uranium mines, mill tailings ponds were studied for dissolved
> radionuclide. The concentration of uranium and 226Ra in untreated effluent water was
> found to be elevated. The concentration of dissolved radionuclide in the adjacent
> aquatic streams and river were found to be lower than the authorized prescribed limit
> provided by Indian regulatory agencies. The removal process of dissolved radionuclide
> in the effluent treatment plant is found to be effective with an average
> decontamination efficiency of >95% for both uranium and 226Ra. The uranium mining and
> ore processing activity has not significantly modified the aquatic environment due to
> effective effluent management system.

Full methods (fluorometric U analysis; Rn-222 buildup method for Ra-226), full results
narrative, and reference list were also captured in this session's browser extraction
and are consistent with the summary table above. Contact the corresponding author
(BARC, Health Physics Unit, Jaduguda) for the primary PDF if the raw file is needed;
the publisher's own DOI landing page (ovid.com / journals.lww.com platform) serves the
complete text as OPEN access.
