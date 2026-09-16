# Demonstration script — eight minutes, one storyline

Written for the final fellowship review (2026-09-16). The storyline is the
proposal's third deliverable read out loud: *a stakeholder inputs data, receives
a vulnerability assessment, and receives an alert.* Every screen below is
reached in that order and nothing is typed that is not on this page.

**Before you start** (five minutes, once):

1. Open the portal in a browser tab and leave it on the front page. The API
   sleeps on Render's free tier; the first request takes ~40 s, so wake it
   before the panel sits down: `curl https://jaldrishti-api.onrender.com/health`.
2. Theme: **light** for a projector (the header toggle; it remembers).
3. Have the four demo accounts from the README visible on a second screen, and
   your own admin sign-in ready.
4. Confirm `Publications → Published` shows the Jaduguda screening and
   `Administration → Alert delivery` shows alerts raised. If either is empty,
   `python -m scripts.seed_demo_story` has not been run against the deployed
   database — see `DEPLOY_WALKTHROUGH.md`.

---

## 1. The front page — "what is this" (60 s)

Do not sign in. Read the hero sentence. Point at the four live tiles: *these are
read from the database on load; nothing here is typed.* Scroll to the premise
box and read the first sentence aloud — **no ISR uranium mine operates in
Jharkhand** — because the panel will otherwise spend the next seven minutes
wondering. Scroll to the map; hover Simdega (nitrate 121 mg/L, 2.7× the limit)
and Lohardaga. Say: *fourteen of twenty-four districts are red, and uranium
decided none of them.*

## 2. Measure — the real record (60 s)

Sign in as **analyst**. Data → **Water quality**. Show the health determinands
first, the general ones second, and the arsenic/iron columns reading *not
tested* everywhere. Say: *the proposal names Fe, Mn and As explicitly; the state
has never measured them, and this screen refuses to colour that green.* Data →
**Groundwater levels**: 8,345 readings, 415 stations, Theil–Sen — five
declining, twenty recovering, most stable. *That is the finding, and it is
undramatic.*

## 3. Model — the engine (120 s)

Map → **Console**. Click **Jaduguda (hypothetical ISR)** in the rail. Show the
resolved hydrogeology on the right: district, lithology, regime *fractured*,
K, flow azimuth, gradient — *resolved from real GSI, CGWB and NAQUIM layers at
that point.* Press **Run**. The map fits to the plume. Read the three numbers:
affected area, migration distance, concentration at the monitoring ring — and
the analytical / ML labels beside them. Toggle **ML + bands** to show the
P10/P90 envelope. Open the **Shallow aquifer** panel: years to breakthrough,
with the seasonal band beside it.

Then click anywhere in **Chatra**. Say: *no ore here, so the engine suppresses
uranium and says so rather than inventing a plume.* That sentence is worth more
than any accuracy figure.

## 4. Decide — publication (60 s)

Sign out; sign in as **your admin account**. Decisions → **Publications →
Published**: open the Jaduguda screening. Show the plain-language text, the
block it reaches (Musabani), the hectares. Say: *analysts propose; only this one
account publishes; a regulator cannot. Publishing is what raised the alerts.*

Administration → **Alert delivery**: read the tiles — alerts raised, people
following, sent, waiting. If email is configured, press **Send waiting emails
now**. If it is not, say so: *the channel is built and idle until a relay is
configured; the count is the proof it is not silent.*

## 5. Receive — the resident (90 s)

Sign out; sign in as **citizen**. Overview → **My area**: the verdict for
Musabani, the determinand scales drawn against their limits, the *assessment
published for your area* card beneath the measured results — measured first,
always. Open **Alerts**: the published-screening alert, its first paragraph
stating the premise. Point at the subtitle: *emailed to the address on the
account.* Open **Map near me**: the public map with the published footprint,
and no site coordinate anywhere.

Then, on the front page, click **Create an account** and show — do not submit —
the *Where do you live?* field with *Use my location*. Say: *the account follows
its own block from the first second; nobody has to predict which block will be
affected.*

## 6. What it does not know (60 s)

Public → **Data & methods**, then scroll the front page to *What this is not*.
Read two lines: *not real-time* and *not validated against a real plume —
none exists.* Then `docs/LIMITATIONS.md` §1: *radium misses our own R² gate,
0.516 against 0.60, and we report it rather than moving the gate.*

Close on the one sentence the whole project rests on: **"No data" is a
monitoring gap, never a clean result — and the product is built so it cannot
say otherwise.**

---

### If asked

* **"Is this a CPS?"** — The sensing layer is a 415-station manual network;
  the threshold → alert → notification → acknowledgement loop is closed and
  logged. *CPS-ready decision support*, not a live loop. `LIMITATIONS.md` §5.
* **"How accurate is the model?"** — Benchmarked against exact analytical
  solutions; the surrogate cannot exceed the engine it was trained on; bands
  are calibrated to ~80 % coverage on the serving distribution. No field
  validation is possible and never will be.
* **"Why Texas?"** — The only public ISR record with before / during / after
  chemistry. Transferred in dimensionless form (Péclet, retardation, pore
  volumes), not as values. Every constant's provenance is in
  `ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md`.
* **"Can a regulator publish?"** — No, and that is deliberate: whoever
  accepts field evidence into the record should not also announce a modelled
  result to a village. `docs/roles.md` is generated from the live route table.
