/**
 * The front page — what a person sees before they have an account.
 *
 * R16. The root URL was a sign-in card. Someone opening the link learned the
 * product's name, that it had roles, and nothing else: not what it measures,
 * not what it models, not that no ISR mine exists in Jharkhand, and not the
 * one map that is public by design. An evaluator had to be told where the
 * demo credentials were before they could see anything at all.
 *
 * WHAT THIS PAGE IS FOR, in order of the questions a first-time viewer asks:
 *
 *   1. What is this?              hero — one sentence, three live numbers
 *   2. Is this real?              the premise, stated before the map
 *   3. Show me.                   the public map, live, no account
 *   4. How does it work?          measure → model → tell people
 *   5. What has it said so far?   published screenings, live
 *   6. Who is it for?             the five roles, and where to sign in
 *   7. What does it NOT claim?    the register's own list, verbatim in spirit
 *
 * EVERY NUMBER HERE IS LIVE. The tiles read `/public/risk/districts` and
 * `/public/risk/advisories`, both unauthenticated by design, so the page
 * cannot drift from the database the way a hand-typed "397 wells" would.
 * When the API is cold (Render sleeps the free tier) the tiles show a dash
 * and the copy still reads correctly.
 *
 * Nothing on this page needs a token, and nothing on it names a site
 * coordinate, a run, or a model band: it is bounded by exactly what
 * `/public/risk/*` returns, which design section 2 already bounds.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import L from "leaflet";
import { api, pub, type PublicDistrictRisk } from "../api/client";
import { attachBasemaps } from "../map/basemaps";
import { Icon, Mark } from "../components/icons";
import { ThemeToggle } from "../theme";
import { useAuth } from "../auth";

const BAND_COLOUR: Record<string, string> = {
  "High concern": "#f2555a",
  "Moderate concern": "#f5a524",
  "Low concern": "#3ecf8e",
  "Not tested": "#8b919c",
  "Not tested for uranium": "#8b919c",
  "No data": "#8b919c",
};

const ROLES: Array<{ label: string; who: string; does: string }> = [
  { label: "Resident", who: "Anyone living in Jharkhand",
    does: "Sees what was measured in their block's groundwater, and is told — in the portal and by email — when a well tests over a limit or a screening is published for their area." },
  { label: "Analyst", who: "CGWB / SPCB / research staff",
    does: "Drops a pin anywhere in the state, resolves the local hydrogeology, runs the transport engine, saves scenarios and proposes a screening for publication." },
  { label: "Regulator", who: "The reviewing officer",
    does: "Decides whether field submissions enter the record. Runs the model to ask 'what if'. Cannot publish, write datasets or manage accounts." },
  { label: "Data submitter", who: "Field officers",
    does: "Files ore occurrences and observations from the ground for review, with the same isolation from the model the audit record enforces." },
  { label: "Administrator", who: "One account, by design",
    does: "The only role that publishes to residents, syncs datasets into the engine, operates the model and reads the audit log." },
];

function fmt(n: number | null | undefined) {
  return n == null ? "—" : n.toLocaleString("en-IN");
}

export default function Landing() {
  const { me } = useAuth();
  const districts = useQuery({
    queryKey: ["landing-districts"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[]; safe_limit: number }>(
      "/public/risk/districts"),
    staleTime: 5 * 60_000,
  });
  const advisories = useQuery({
    queryKey: ["landing-advisories"], queryFn: pub.advisories, staleTime: 5 * 60_000,
  });
  const geo = useQuery({
    queryKey: ["landing-geo"],
    queryFn: () => api.get<GeoJSON.FeatureCollection>("/public/risk/geojson/districts"),
    staleTime: 10 * 60_000,
  });

  const stats = useMemo(() => {
    const d = districts.data?.districts ?? [];
    if (!d.length) return null;
    return {
      districts: d.length,
      wells: d.reduce((a, x) => a + (x.wells ?? 0), 0),
      high: d.filter((x) => x.band === "High concern").length,
      untested: d.filter((x) => x.band.startsWith("Not tested") || x.band === "No data").length,
    };
  }, [districts.data]);

  // ── the public map ──
  const mapEl = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.GeoJSON | null>(null);
  const [hover, setHover] = useState<PublicDistrictRisk | null>(null);

  useEffect(() => {
    if (!mapEl.current || map.current) return;
    const m = L.map(mapEl.current, {
      zoomControl: false, attributionControl: true, scrollWheelZoom: false,
      dragging: !L.Browser.mobile,
    }).setView([23.6, 85.4], 7);
    attachBasemaps(m, "light");
    L.control.zoom({ position: "bottomright" }).addTo(m);
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m || !geo.data) return;
    layer.current?.remove();
    const byId = new Map((districts.data?.districts ?? []).map((d) => [d.id, d]));
    const g = L.geoJSON(geo.data, {
      style: (f) => {
        const p: any = f?.properties ?? {};
        const c = BAND_COLOUR[p.band] ?? "#8b919c";
        return { color: c, weight: 1.2, fillColor: c, fillOpacity: 0.32 };
      },
      onEachFeature: (f, l) => {
        const p: any = f.properties ?? {};
        const d = byId.get(p.id) ?? p;
        l.on("mouseover", () => { setHover(d); (l as L.Path).setStyle({ fillOpacity: 0.55 }); });
        l.on("mouseout", () => { setHover(null); (l as L.Path).setStyle({ fillOpacity: 0.32 }); });
        l.bindTooltip(`<b>${p.name}</b><br>${p.band ?? ""}`, { sticky: true, className: "plume-tip" });
      },
    }).addTo(m);
    layer.current = g;
    try { m.fitBounds(g.getBounds().pad(0.04)); } catch { /* empty collection */ }
  }, [geo.data, districts.data]);

  const published = advisories.data?.advisories ?? [];

  return (
    <div className="landing">
      <header className="ld-head">
        <Link to="/" className="hdr-brand" style={{ textDecoration: "none", color: "inherit" }}>
          <Mark size={30} />
          <div>
            <div className="hdr-name">JalDrishti</div>
            <div className="hdr-sub">Groundwater screening · Jharkhand</div>
          </div>
        </Link>
        <nav className="ld-nav" aria-label="Sections">
          <a href="#map">Public map</a>
          <a href="#how">How it works</a>
          <a href="#published">Published</a>
          <a href="#roles">Who it is for</a>
          <a href="#honest">What it is not</a>
        </nav>
        <div className="row" style={{ gap: 8 }}>
          <ThemeToggle />
          {me ? (
            <Link to="/overview" className="btn primary">Open the portal <Icon name="arrow" size={15} /></Link>
          ) : (
            <>
              <Link to="/login" className="btn">Sign in</Link>
              <Link to="/register" className="btn primary">Create an account</Link>
            </>
          )}
        </div>
      </header>

      {/* ── 1. hero ── */}
      <section className="ld-hero">
        <div className="ld-hero-copy">
          <div className="eyebrow">TEXMiN – BIT Sindri · UG fellowship 2025–26 · Mine safety with AI/ML &amp; CPS</div>
          <h1>
            Know what a uranium mine would do to the groundwater
            <span className="accent"> before anyone proposes one.</span>
          </h1>
          <p className="lede">
            JalDrishti reads Jharkhand's real groundwater record — 397 government
            wells, nine years of water-level measurements — judges it against the
            Indian drinking-water standard, and models how contamination from a
            hypothetical in-situ recovery operation would spread through the rock
            beneath any point in the state. Then it tells the people who live there.
          </p>
          <div className="row wrap" style={{ gap: 10, marginTop: 18 }}>
            <a href="#map" className="btn primary lg"><Icon name="map" /> Open the public map</a>
            <Link to="/login" className="btn lg">Walk the roles <Icon name="arrow" size={15} /></Link>
          </div>
        </div>
        <div className="ld-stats" aria-label="Live figures from the public record">
          <div className="ld-stat">
            <div className="v">{fmt(stats?.districts)}</div>
            <div className="k">districts assessed</div>
          </div>
          <div className="ld-stat">
            <div className="v">{fmt(stats?.wells)}</div>
            <div className="k">government wells read against IS 10500</div>
          </div>
          <div className="ld-stat danger">
            <div className="v">{fmt(stats?.high)}</div>
            <div className="k">districts with a measured health exceedance</div>
          </div>
          <div className="ld-stat">
            <div className="v">{fmt(advisories.data?.count)}</div>
            <div className="k">screenings published to residents</div>
          </div>
          <div className="ld-stat-note">
            Live from the database. {stats && stats.untested > 0 &&
              `${stats.untested} district${stats.untested === 1 ? "" : "s"} carry no health result at all — a monitoring gap, never a pass.`}
          </div>
        </div>
      </section>

      {/* ── 2. premise ── */}
      <section className="ld-premise" role="note">
        <Icon name="alert" size={22} />
        <div>
          <strong>No ISR uranium mine operates in Jharkhand, and none is planned.</strong>{" "}
          Every site in this system is hypothetical. Every modelled figure means
          <em> “if lixiviant of ISR strength entered this aquifer”</em> — never
          feasibility, never a permit, never a report of an event. The measured
          figures are different: those are laboratory results from wells people
          drink from today.
        </div>
      </section>

      {/* ── 3. the public map ── */}
      <section id="map" className="ld-section">
        <div className="ld-section-head">
          <h2>The public map</h2>
          <p>
            Districts coloured by the worst measured health determinand in their
            wells — uranium, nitrate or fluoride — against IS 10500:2012. Grey is
            never green: a district with no result is a gap in monitoring, not a
            clean bill.
          </p>
        </div>
        <div className="ld-map-wrap">
          <div ref={mapEl} className="ld-map" aria-label="Jharkhand districts by measured health concern" />
          <aside className="ld-map-side">
            {hover ? (
              <>
                <div className="eyebrow">{hover.name}</div>
                <div className="ld-band" style={{ color: BAND_COLOUR[hover.band] }}>{hover.band}</div>
                <div className="muted small">
                  {hover.wells} wells sampled
                  {hover.band_driver && ` · decided by ${hover.band_driver}`}
                </div>
                <dl className="ld-dl">
                  <dt>Uranium</dt><dd>{hover.max_uranium_ppb ?? "not tested"} {hover.max_uranium_ppb != null && "ppb"}</dd>
                  <dt>Nitrate</dt><dd>{hover.max_nitrate_mg_l ?? "—"} {hover.max_nitrate_mg_l != null && "mg/L"}</dd>
                  <dt>Fluoride</dt><dd>{hover.max_fluoride_mg_l ?? "—"} {hover.max_fluoride_mg_l != null && "mg/L"}</dd>
                </dl>
                {!!hover.untested_health?.length && (
                  <div className="muted small">Never analysed here: {hover.untested_health.join(", ")}.</div>
                )}
              </>
            ) : (
              <>
                <div className="eyebrow">Hover a district</div>
                <div className="muted small" style={{ marginTop: 6 }}>
                  Maximum measured value per determinand, and which one decided the band.
                </div>
                <div className="ld-legend">
                  {["High concern", "Moderate concern", "Low concern", "Not tested"].map((b) => (
                    <div key={b} className="row"><span className="sw" style={{ background: BAND_COLOUR[b] }} />{b}</div>
                  ))}
                </div>
                <div className="muted small" style={{ marginTop: 10 }}>
                  Sign in as a resident to go to block level, follow your area and receive alerts.
                </div>
              </>
            )}
          </aside>
        </div>
      </section>

      {/* ── 4. how it works ── */}
      <section id="how" className="ld-section">
        <div className="ld-section-head">
          <h2>How it works</h2>
          <p>Three parts, wired together, each honest about what it is.</p>
        </div>
        <div className="ld-steps">
          <div className="ld-step">
            <div className="n"><Icon name="flask" /></div>
            <h3>Measure</h3>
            <p>
              The real record first. 397 CGWB wells, twenty determinands each, judged
              against IS 10500; 8,345 water-level readings from 415 stations over
              2013–2021, tested for trend with Theil–Sen and Mann–Kendall. Nothing here
              is modelled.
            </p>
          </div>
          <div className="ld-step">
            <div className="n"><Icon name="layers" /></div>
            <h3>Model</h3>
            <p>
              A 2-D contaminant-transport engine — Domenico advection–dispersion with
              matrix diffusion for fractured rock — grounded in Texas ISR operating
              records and Jharkhand's own aquifers, flow field and ore bodies. An XGBoost
              surrogate trained on that engine adds calibrated P10/P50/P90 bands and
              flags when a request leaves its trained range.
            </p>
          </div>
          <div className="ld-step">
            <div className="n"><Icon name="send" /></div>
            <h3>Tell people</h3>
            <p>
              A screening reaches residents only when the administrator publishes it.
              Publication alerts every block the footprint touches and every block that
              shares the shallow aquifer a modelled pathway would enter; a measured
              exceedance alerts on its own. Each alert is logged, delivered by email,
              and readable in the portal.
            </p>
          </div>
        </div>
      </section>

      {/* ── 5. published ── */}
      <section id="published" className="ld-section">
        <div className="ld-section-head">
          <h2>Published screenings</h2>
          <p>
            What the authority operating this platform has put in front of residents.
            Plain language, the blocks concerned, and no site coordinate — that stays
            off every public surface by design.
          </p>
        </div>
        {advisories.isLoading && <div className="muted">Loading…</div>}
        {advisories.data && published.length === 0 && (
          <div className="ld-empty">Nothing has been published yet.</div>
        )}
        <div className="ld-pubs">
          {published.slice(0, 4).map((a) => (
            <article key={a.id} className="ld-pub">
              <div className="row wrap" style={{ gap: 8 }}>
                <span className="chip warn">Modelled screening</span>
                {a.published_at && (
                  <span className="muted small">
                    {new Date(a.published_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}
                  </span>
                )}
              </div>
              <h3>{a.headline}</h3>
              <p>{a.what_it_means}</p>
              <div className="muted small">
                {a.blocks.map((b) => b.name).filter(Boolean).join(", ")}
                {a.footprint_ha != null && ` · about ${a.footprint_ha.toFixed(1)} ha modelled`}
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ── 6. roles ── */}
      <section id="roles" className="ld-section">
        <div className="ld-section-head">
          <h2>Who it is for</h2>
          <p>
            Five roles, enforced three times over: in the interface, at the API, and by
            Postgres row-level security. A resident never sees a site coordinate; a
            regulator never publishes; only one account administers.
          </p>
        </div>
        <div className="ld-roles">
          {ROLES.map((r) => (
            <div key={r.label} className="ld-role">
              <div className="eyebrow">{r.who}</div>
              <h3>{r.label}</h3>
              <p>{r.does}</p>
            </div>
          ))}
        </div>
        <div className="row wrap" style={{ gap: 10, marginTop: 16 }}>
          <Link to="/register" className="btn primary lg">Create a resident account</Link>
          <Link to="/login" className="btn lg">Sign in as staff</Link>
          <span className="muted small">
            Demonstration accounts for each role are listed in the{" "}
            <a href="https://github.com/VishalRaj720/JalDrishti#demo-accounts" target="_blank" rel="noreferrer noopener">
              project README <Icon name="external" size={12} />
            </a>.
          </span>
        </div>
      </section>

      {/* ── 7. what it is not ── */}
      <section id="honest" className="ld-section ld-honest">
        <div className="ld-section-head">
          <h2>What this is not</h2>
          <p>Written down because these are the claims most likely to be overstated.</p>
        </div>
        <ul>
          <li><strong>Not real-time.</strong> There is no sensor feed. The measured record is CGWB campaign sampling, and the trends describe 2013–2021 rather than forecasting anything.</li>
          <li><strong>Not validated against a real plume.</strong> None exists to validate against. The engine is benchmarked against exact analytical solutions; the bands quantify parameter uncertainty, not structural error.</li>
          <li><strong>Not a health determination.</strong> The IS 10500 assessment compares a laboratory value with a published limit. It says nothing about exposure or treatment.</li>
          <li><strong>“Low concern” is not a clean bill.</strong> Arsenic and iron were analysed nowhere in the state, so no block has been fully cleared, and every result says which substances were never looked for.</li>
          <li><strong>Not a permit, a plan or a feasibility study.</strong> Commercial ISR is not physically plausible in schist-hosted ore, and every output means only <em>“if lixiviant entered this aquifer”.</em></li>
        </ul>
        <div className="muted small">
          The full register of what this system does not know is <code>docs/LIMITATIONS.md</code> in the repository.
        </div>
      </section>

      <footer className="ld-foot">
        <div className="row wrap" style={{ gap: 14 }}>
          <Mark size={22} />
          <span>JalDrishti · Smart Water Monitoring: Machine Learning and CPS for Safe &amp; Sustainable Mining</span>
        </div>
        <div className="muted small">
          B.I.T. Sindri · TEXMiN CoE · Vishal Raj, Information Technology (2024–28) · Data: CGWB, GSI, USGS, IAEA UDEPO, NAQUIM
        </div>
      </footer>
    </div>
  );
}
