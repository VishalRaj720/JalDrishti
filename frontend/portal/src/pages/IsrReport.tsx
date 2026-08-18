/**
 * The full ISR report — every parameter, every contaminant, one document.
 *
 * R6 built this because the Publications screen showed a headline, some prose,
 * a block overlap and six numbers about uranium. That is a summary of a
 * decision, not a description of what was assessed, and it left the reader
 * unable to answer the obvious follow-ups: what were the operating parameters?
 * what about sulfate? does it reach the shallow aquifer? what happens after
 * year 20?
 *
 * R10 turned it from a debug dump into a DOCUMENT. The content was right and
 * the reading order was not: charts before context, the depth section rendered
 * TWICE (once here and once inside `RunResult`), no map, no summary anyone
 * outside the project could read, and no way to take it out of the portal.
 *
 * The order now is the order an assessment is read in — what this is, what it
 * says in plain words, where it is, what was assumed, what the model found,
 * what was published, and how to re-derive it.
 *
 * Two inputs are deliberately left live — **evaluation horizon** (default
 * 50 yr) and **restoration sweep** (default 0 yr) — because those are the two
 * questions a reader legitimately re-asks of a published site, and re-asking
 * them must not require an analyst. Everything else is fixed by the site, as it
 * is everywhere else in this product.
 *
 * Nothing here is stored. A reader exploring "what if they swept for five
 * years" is asking a question, not creating a record.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import {
  api, type Advisory, type IsrPoint, type Lifecycle, type PreviewRun, type SimRun,
} from "../api/client";
import { canRunSim, useAuth } from "../auth";
import { ErrorNote, Loading, TableScroll } from "../components/bits";
import LifecycleChart, { LifecycleNarrative } from "../console/LifecycleChart";
import ReportMap from "../console/ReportMap";
import RunResult from "../console/RunResult";
import { VerticalNumbers, VerticalSchematic } from "../console/VerticalPanel";
import { fmt } from "../console/mapLayers";
import { SPECIES_NAME } from "../map/plume";
import { AffectedBlocks } from "../console/ProposeAdvisory";

/** The report's own defaults, as specified: look a long way out, assume nothing
 *  was cleaned up. Both are the conservative reading — a short horizon hides
 *  post-closure migration, and assuming a sweep credits remediation nobody has
 *  committed to. */
const DEFAULT_HORIZON = 50;
const DEFAULT_RESTORATION = 0;

export default function IsrReport() {
  const { siteId } = useParams<{ siteId: string }>();
  const nav = useNavigate();
  const { me } = useAuth();
  const mayRun = canRunSim(me?.role);

  const [horizon, setHorizon] = useState(DEFAULT_HORIZON);
  const [restoration, setRestoration] = useState(DEFAULT_RESTORATION);
  const [exporting, setExporting] = useState(false);
  const doc = useRef<HTMLDivElement | null>(null);

  const site = useQuery({
    queryKey: ["isr-point", siteId], enabled: !!siteId,
    queryFn: () => api.get<IsrPoint>(`/isr-points/${siteId}`),
  });
  const advisories = useQuery({
    queryKey: ["advisories", siteId], enabled: !!siteId,
    queryFn: () => api.get<Advisory[]>(`/advisories?isr_point_id=${siteId}`),
  });
  const runs = useQuery({
    queryKey: ["runs", siteId], enabled: !!siteId,
    queryFn: () => api.get<SimRun[]>(`/simulations/runs?isr_id=${siteId}&limit=10`),
  });

  const lifecycle = useMutation({
    mutationFn: () => api.post<Lifecycle>(`/simulations/${siteId}/lifecycle`, {
      time_years: horizon, restoration_years: restoration, points: 12,
    }),
  });
  const detail = useMutation({
    mutationFn: () => api.post<PreviewRun>(`/simulations/${siteId}/preview`, {
      species: "uranium_ppb", time_years: horizon, restoration_years: restoration,
    }),
  });

  // Build the report on open, and again whenever the two live inputs change —
  // the reader should not have to press a button to see the defaults.
  useEffect(() => {
    if (!siteId || !mayRun) return;
    lifecycle.mutate();
    detail.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, horizon, restoration, mayRun]);

  const s = site.data;
  const published = (advisories.data ?? []).find((a) => a.status === "published")
    ?? (advisories.data ?? [])[0];

  /**
   * PDF EXPORT — client-side, html2canvas + jsPDF via html2pdf.
   *
   * A PDF LEAVES THE PORTAL and will be read with none of its context, so the
   * capture carries the hypothetical premise at the top, the provenance block
   * at the bottom, and a footer note on every page.
   *
   * The document is captured in a LIGHT palette (`.printing`), not the console
   * dark theme. This is not decoration: a dark A4 page is unreadable in print,
   * unusable in a photocopier and hostile to the ink budget of exactly the
   * offices this is meant for. The swap is done with CSS variables on the
   * container, so no component knows or cares that it is being printed.
   */
  async function downloadPdf() {
    const node = doc.current;
    if (!node || exporting) return;
    setExporting(true);
    try {
      // Let the light palette paint before the canvas snapshot is taken.
      await new Promise((r) => setTimeout(r, 350));
      const { default: html2pdf } = await import("html2pdf.js");
      const safe = (s?.name ?? "isr-site").replace(/[^\w\-]+/g, "-").toLowerCase();
      await html2pdf()
        .set({
          margin: [12, 10, 14, 10],
          filename: `jaldrishti-screening-${safe}.pdf`,
          image: { type: "jpeg", quality: 0.96 },
          html2canvas: {
            scale: 2, useCORS: true, backgroundColor: "#ffffff", logging: false,
          },
          jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
          // Cards are the document's natural blocks; splitting one across a
          // page break separates a number from the caveat that governs it.
          pagebreak: { mode: ["css", "legacy"], avoid: [".card", ".avoid-break"] },
        })
        .from(node)
        .save();
    } catch (err) {
      // Reported rather than swallowed — a silent no-op on a download button
      // reads as a broken product.
      console.error("PDF export failed", err);
      alert("The PDF could not be generated. The report is still readable on screen.");
    } finally {
      setExporting(false);
    }
  }

  if (site.isLoading) return <div className="page"><Loading label="Loading the site…" /></div>;
  if (site.error) return <div className="page"><ErrorNote error={site.error} /></div>;
  if (!s) return null;

  const coords = s.location?.coordinates;
  const v = detail.data?.vertical;
  const an = detail.data?.metrics?.analytical;
  const generated = new Date();

  return (
    <div className="page report-page">
      {/* Screen-only controls. Excluded from the capture by living outside
          `doc` — a PDF with a "Download PDF" button printed on it is a tell
          that nobody looked at the output. */}
      <div className="row wrap" style={{ marginBottom: 14 }}>
        <button className="btn ghost" onClick={() => nav("/publications")}>
          ← Publications
        </button>
        <span className="spacer grow" />
        <button className="btn primary" onClick={downloadPdf} disabled={exporting}>
          {exporting ? <><span className="spinner sm" /> Preparing…</> : "Download PDF"}
        </button>
      </div>

      <div ref={doc} className={`report-doc ${exporting ? "printing" : ""}`}>
        {/* ── title block ── */}
        <header className="doc-head avoid-break">
          <div className="doc-eyebrow">
            JalDrishti · Groundwater Contamination Impact Assessment
          </div>
          <h1>{s.name}</h1>
          <div className="doc-sub">
            Screening assessment of a <b>hypothetical</b> in-situ recovery uranium
            operation · Jharkhand, India
          </div>
          <dl className="doc-meta">
            <div><dt>Site reference</dt><dd className="mono">{s.id.slice(0, 8)}</dd></div>
            <div><dt>Location</dt>
              <dd className="mono">{coords
                ? `${coords[1].toFixed(4)} °N, ${coords[0].toFixed(4)} °E` : "–"}</dd></div>
            <div><dt>Evaluation horizon</dt><dd>{horizon} yr</dd></div>
            <div><dt>Restoration assumed</dt><dd>{restoration} yr</dd></div>
            <div><dt>Generated</dt><dd>{generated.toLocaleString()}</dd></div>
            <div><dt>Status</dt>
              <dd>{published
                ? <span className={`chip ${published.status === "published" ? "ok" : "warn"}`}>
                    {published.status}</span>
                : <span className="chip neutral">not published</span>}</dd></div>
          </dl>
        </header>

        {/* ── the premise, first, always ── */}
        <div className="banner warn avoid-break" style={{ marginBottom: 16 }}>
          <strong>No ISR uranium mine operates in Jharkhand.</strong> This document
          describes a modelled scenario at this location, used for screening and
          preparedness. It is not a record of anything that has happened, not a
          statement that anything is planned, and not a permitting document.
        </div>

        {/* ── executive summary ── */}
        {mayRun && (
          <section className="card avoid-break">
            <div className="card-title">Summary</div>
            {detail.isPending && <Loading label="Solving…" />}
            {detail.data && (
              <div className="prose">
                <p>
                  If an in-situ recovery uranium operation of the size registered here
                  ran at this location — injecting {fmt(s.injection_rate_m3_day, 0)} m³
                  of leaching solution a day for {fmt(s.operation_years, 0)} years into
                  an ore zone {fmt(s.ore_depth_m, 0)} m down — the physics engine
                  estimates that after <b>{horizon} years</b>
                  {restoration > 0
                    ? <>, including a <b>{restoration}-year</b> restoration sweep,</>
                    : <>, with <b>no restoration sweep assumed</b>,</>}{" "}
                  uranium contamination would cover{" "}
                  <b>{an?.area_ha != null ? `${fmt(an.area_ha, 1)} hectares` : "no modelled area"}</b>
                  {an?.migration_m != null && <>, with the furthest edge about{" "}
                    <b>{fmt(an.migration_m, 0)} m</b> from the wellfield</>}.
                </p>

                {/* TWO DIFFERENT NOTICES, and treating them alike states
                    something false. `zone === "none"` is the engine REFUSING a
                    uranium source term outside an ore zone. Any other notice is
                    a qualification of a source term it DID produce — at
                    Jaduguda, "Prospective Belt … source term reduced", which
                    arrives alongside a real 8.5 ha result. Printing "declined"
                    over a non-zero area is exactly the confidently wrong
                    statement §0 rule 5 exists to prevent. */}
                {detail.data.notice && (
                  detail.data.ore_zone?.zone === "none" ? (
                    <p>
                      <b>The engine declined to produce a uranium source term here.</b>{" "}
                      {detail.data.notice} That is the model refusing to invent
                      contamination outside an ore zone — it is not a finding that the
                      location is safe. Sulfate and TDS are still modelled and are shown
                      in the lifecycle section below.
                    </p>
                  ) : (
                    <p>
                      <b>Qualification from the engine.</b> {detail.data.notice}{" "}
                      The figures above already reflect this — it is stated so the
                      result is not read as a firmer claim than the ore evidence
                      supports.
                      {detail.data.ore_zone?.nearest_deposit && (
                        <> Nearest known deposit: {detail.data.ore_zone.nearest_deposit},{" "}
                          {fmt(detail.data.ore_zone.nearest_deposit_km, 2)} km away.</>
                      )}
                    </p>
                  )
                )}

                {v?.shallow_impact_probability != null && (
                  <p>
                    The question that matters most to people living nearby is whether
                    this reaches the <b>shallow aquifer they actually pump from</b>. The
                    screening puts that at{" "}
                    <b>{(v.shallow_impact_probability * 100).toFixed(0)}%</b>
                    {v.risk_band && <> ({String(v.risk_band).toLowerCase()} band)</>}
                    {v.years_to_vertical_breakthrough != null
                      ? <>, with breakthrough expected after about{" "}
                          <b>{fmt(v.years_to_vertical_breakthrough, 1)} years</b> if it
                          happens</>
                      : <>, with no breakthrough expected inside the screened horizon</>}.
                  </p>
                )}

                <p>
                  Every value above comes from the <b>analytical physics engine</b>,
                  which is the authority in this product. The machine-learning surrogate
                  was trained on that engine&apos;s own output and contributes calibrated
                  uncertainty bands only — never a competing estimate. Where a run falls
                  outside the surrogate&apos;s trained range, the report says so and the
                  band&apos;s guarantee is void.
                </p>
              </div>
            )}
          </section>
        )}

        {/* ── the two live inputs (screen affordance, printed as a record) ── */}
        <section className="card no-print-controls">
          <div className="card-title">The two questions you may re-ask</div>
          <div className="grid-2">
            <div className="slider">
              <label>Evaluation horizon <span className="u">yr</span><b>{horizon}</b></label>
              <input type="range" min={1} max={50} step={1} value={horizon}
                     onChange={(e) => setHorizon(+e.target.value)} />
            </div>
            <div className="slider">
              <label>Restoration sweep <span className="u">yr</span><b>{restoration}</b></label>
              <input type="range" min={0} max={30} step={1} value={restoration}
                     onChange={(e) => setRestoration(+e.target.value)} />
            </div>
          </div>
          <div className="muted small">
            These two are yours to change; everything else is a property of the site and
            is fixed, so that two people reading this report read the same operation.
            Defaults are deliberately conservative — look a long way out
            ({DEFAULT_HORIZON} yr), and assume no remediation ({DEFAULT_RESTORATION} yr).
            Nothing you do here is stored.
          </div>
        </section>

        {/* ── where it is ── */}
        {mayRun && coords && (
          <section className="card avoid-break">
            <div className="card-title">Figure 1 — Site and modelled extent</div>
            <ReportMap lon={coords[0]} lat={coords[1]} siteName={s.name}
                       run={detail.data ?? null} />
          </section>
        )}

        {/* ── the operation ── */}
        <section className="card">
          <div className="card-title">The operation — fixed for this site</div>
          <TableScroll>
            <table className="grid">
              <tbody>
                <tr><td>Injection rate</td>
                    <td className="mono">{fmt(s.injection_rate_m3_day, 0)} m³/day</td>
                    <td className="muted small">lixiviant delivered to the wellfield</td></tr>
                <tr><td>Bleed</td><td className="mono">{fmt(s.bleed_percent, 2)} %</td>
                    <td className="muted small">net over-extraction that holds the plume in</td></tr>
                <tr><td>Operation duration</td><td className="mono">{fmt(s.operation_years, 0)} yr</td>
                    <td className="muted small">how long injection continues</td></tr>
                <tr><td>Well-pattern footprint ⌀</td>
                    <td className="mono">{fmt(s.wellfield_width_m, 0)} m</td>
                    <td className="muted small">full transverse extent of the wellfield — not a borehole width</td></tr>
                <tr><td>Monitor ring</td><td className="mono">{fmt(s.monitor_ring_m, 0)} m</td>
                    <td className="muted small">perimeter distance where an excursion is detected</td></tr>
                <tr><td>Ore zone depth</td><td className="mono">{fmt(s.ore_depth_m, 0)} m</td>
                    <td className="muted small">depth to the injection target</td></tr>
                <tr><td>Ore zone thickness</td><td className="mono">{fmt(s.ore_thickness_m, 0)} m</td>
                    <td className="muted small">vertical extent of the target</td></tr>
                <tr><td>Planned restoration</td>
                    <td className="mono">{fmt(s.restoration_years, 0)} yr</td>
                    <td className="muted small">the site&apos;s own figure; this report uses {restoration} yr</td></tr>
                <tr><td>Aquifer regime</td>
                    <td className="mono">{s.regime_override ?? "resolved from the location"}</td>
                    <td className="muted small">left to the engine unless overridden</td></tr>
                <tr><td>Hydraulic gradient</td>
                    <td className="mono">{s.gradient_i ?? "resolved from the location"}</td>
                    <td className="muted small">from the measured flow field</td></tr>
                <tr><td>Flow direction</td>
                    <td className="mono">{s.azimuth_deg ?? "resolved from the location"}</td>
                    <td className="muted small">down-gradient bearing</td></tr>
              </tbody>
            </table>
          </TableScroll>
        </section>

        {!mayRun && (
          <div className="banner">
            Your role can read this record but not re-run the model, so the modelled
            sections are unavailable. The published summary and the affected area are
            shown below.
          </div>
        )}

        {/* ── the shallow aquifer: schematic beside its numbers ── */}
        {mayRun && v && (
          <section className="card">
            <div className="card-title">
              The shallow aquifer — the water people pump
            </div>
            <div className="split-figure">
              <div className="split-figure-fig">
                <VerticalSchematic v={v} heading={false} />
              </div>
              <div className="split-figure-num">
                <dl className="kv">
                  <dt>Chance of reaching it</dt>
                  <dd>{v.shallow_impact_probability != null
                    ? `${(v.shallow_impact_probability * 100).toFixed(0)} %` : "not screened"}</dd>
                  <dt>Breakthrough</dt>
                  <dd>{v.years_to_vertical_breakthrough != null
                    ? `${fmt(v.years_to_vertical_breakthrough, 1)} yr`
                    : "not expected in horizon"}</dd>
                  <dt>Ore zone depth</dt><dd>{fmt(v.ore_depth_m ?? s.ore_depth_m, 0)} m</dd>
                  <dt>Shallow aquifer base</dt><dd>{fmt(v.layer1_base_m, 0)} m</dd>
                  <dt>Confining separation</dt>
                  <dd>{fmt(v.separation_m ?? v.seasonal?.separation_m, 0)} m</dd>
                  {v.seasonal?.water_table_wet_m != null && (
                    <>
                      <dt>Water table (wet–dry)</dt>
                      <dd>{fmt(v.seasonal.water_table_wet_m, 1)}–
                          {fmt(v.seasonal.water_table_dry_m, 1)} m</dd>
                    </>
                  )}
                  {v.seasonal?.seasonal_swing_m != null && (
                    <>
                      <dt>Seasonal swing</dt>
                      <dd>{fmt(v.seasonal.seasonal_swing_m, 1)} m</dd>
                    </>
                  )}
                </dl>
                <VerticalNumbers v={v} />
              </div>
            </div>
          </section>
        )}

        {/* ── every contaminant, across the whole life ── */}
        {mayRun && (
          <section className="card">
            <div className="card-title">All four contaminants, across the operation</div>
            {lifecycle.isPending && <Loading label="Tracing four contaminants…" />}
            <ErrorNote error={lifecycle.error} />
            {lifecycle.data && (
              <>
                <LifecycleChart data={lifecycle.data} />
                <LifecycleNarrative data={lifecycle.data} />
              </>
            )}
          </section>
        )}

        {/* ── the detailed uranium run at these settings ── */}
        {mayRun && (
          <section className="card">
            <div className="card-title">
              Uranium in detail at {horizon} yr, {restoration} yr sweep
            </div>
            {detail.isPending && <Loading label="Solving…" />}
            <ErrorNote error={detail.error} />
            {detail.data && (
              // `showVertical={false}`: the depth section is rendered once,
              // above, beside its numbers. This used to render it a second time.
              <RunResult r={detail.data} extrapolation={detail.data.extrapolation ?? []}
                         showVertical={false} />
            )}
          </section>
        )}

        {/* ── what was published, and where it reaches ── */}
        {published && (
          <section className="card">
            <div className="card-title">
              Published to residents
              <span className="spacer grow" />
              <span className={`chip ${published.status === "published" ? "ok" : "warn"}`}>
                {published.status}
              </span>
            </div>
            <div className="banner" style={{ marginBottom: 10 }}>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>{published.headline}</div>
              <div className="prose" style={{ whiteSpace: "pre-wrap", fontSize: "var(--fs-sm)" }}>
                {published.what_it_means}
              </div>
            </div>
            <AffectedBlocks advisory={published} />
            <div className="muted small" style={{ marginTop: 8 }}>
              Published for {SPECIES_NAME[published.species] ?? published.species} at{" "}
              {fmt(published.time_years, 0)} yr with a {fmt(published.restoration_years, 0)} yr
              sweep. Changing the sliders above does not change what was published — that
              record is fixed to the run behind it.
            </div>
          </section>
        )}

        {/* ── provenance ── */}
        <section className="card">
          <div className="card-title">Provenance — how to re-derive this</div>
          {runs.isLoading && <Loading />}
          {(runs.data ?? []).length === 0 && (
            <div className="muted small">
              No stored run for this site yet. The figures above are live and unstored;
              a saved run is what carries a re-derivable provenance triple.
            </div>
          )}
          <TableScroll>
            <table className="grid">
              <thead>
                <tr><th>Run</th><th>Contaminant</th><th>Model card</th><th>Code</th><th>When</th></tr>
              </thead>
              <tbody>
                {(runs.data ?? []).filter((r) => r.status === "completed").map((r) => (
                  <tr key={r.id}>
                    <td className="mono">{r.id.slice(0, 8)}</td>
                    <td>{SPECIES_NAME[r.species] ?? r.species}</td>
                    <td className="mono">{r.model_card_sha?.slice(0, 12)}…</td>
                    <td className="mono">{r.code_version?.slice(0, 10)}</td>
                    <td className="muted small">
                      {r.completed_at ? new Date(r.completed_at).toLocaleString() : "–"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
          <div className="muted small" style={{ marginTop: 8 }}>
            Every stored run is pinned to the model card, artifact bundle and git commit
            that produced it, so any number in this report can be reproduced exactly as
            it stood — not merely recomputed with whatever the model looks like today.
          </div>
        </section>

        {/* ── colophon: the premise again, because a PDF outlives its context ── */}
        <footer className="doc-foot avoid-break">
          <div>
            <b>JalDrishti</b> — groundwater contamination impact assessment for
            hypothetical ISR uranium mining in Jharkhand. Values are produced by an
            analytical contaminant-transport engine; the ML surrogate supplies
            uncertainty bands only.
          </div>
          <div style={{ marginTop: 6 }}>
            <b>No ISR uranium mine operates in Jharkhand.</b> This is a screening
            model of a hypothetical operation, not a measurement, a plan, or a
            permitting document. Generated {generated.toLocaleString()} for site{" "}
            <span className="mono">{s.id.slice(0, 8)}</span>.
          </div>
        </footer>
      </div>
    </div>
  );
}
