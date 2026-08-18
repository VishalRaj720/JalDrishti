/**
 * Data & Methods — the assumption register, in plain language.
 *
 * A named deliverable of the proposal ("identify key data gaps... and recommend
 * improved monitoring strategies") and the thing that makes the rest of the
 * portal checkable rather than merely confident. A citizen or a journalist
 * should be able to see what the numbers rest on without reading the code.
 *
 * The engine already maintains an honest register of what it does not know
 * (`UNGROUNDED_PARAMETERS` in `ml_pipeline/config/parameters.py`, served at
 * `/ml/assumptions`). Staff get it live from there. Everyone gets the
 * plain-language version below, which is written here rather than generated,
 * because a limitation phrased for a hydrogeologist is not a limitation a
 * resident can act on.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { isStaff, useAuth } from "../auth";
import { Loading, TableScroll } from "../components/bits";

const PLAIN: Array<{ q: string; a: string }> = [
  {
    q: "Is there a uranium mine of this kind in Jharkhand?",
    a: "No. No in-situ recovery uranium operation exists anywhere in Jharkhand, and "
     + "none is proposed here. This platform models what would happen if one were "
     + "built, so that regulators and communities can prepare rather than react. "
     + "Every assessment on this site says so.",
  },
  {
    q: "Then what is real on this site?",
    a: "The measurements. Groundwater test results come from the Central Ground Water "
     + "Board's published monitoring network — real wells, real laboratory results, "
     + "real dates. When an alert says a well tested above the safe limit, that "
     + "happened. Only the mine scenarios are modelled.",
  },
  {
    q: "What is the safe limit?",
    a: "30 parts per billion (ppb) of uranium in drinking water, the Bureau of Indian "
     + "Standards limit, which matches the World Health Organization guideline.",
  },
  {
    q: "My block says “No data”. Does that mean the water is safe?",
    a: "No — and this is the most important thing on this page. “No data” means no "
     + "well in that block has been sampled in the dataset we use. It is a gap in "
     + "monitoring, not a clean result. The water may be fine; nobody has checked.",
  },
  {
    q: "How accurate are the model's numbers?",
    a: "The model gives a range, not a single answer, and that range was checked "
     + "against held-out data from real Jharkhand hydrogeology. Outside the "
     + "conditions it was trained on, the portal marks the result as unreliable "
     + "rather than hiding it. Some inputs — particularly the fine structure of "
     + "fractured rock near Singhbhum — have no local measurements behind them at "
     + "all, and the register below names them.",
  },
  {
    q: "Why blocks and not my village?",
    a: "Because there is no village-level groundwater dataset to draw on. A block is "
     + "the finest area the available data honestly supports. Offering a village "
     + "search that quietly resolved to a block would imply a precision we do not "
     + "have.",
  },
  {
    q: "Does this portal do its own fieldwork?",
    a: "No. Everything here is built from published government datasets and "
     + "literature. The only field input it accepts is the recorded presence of "
     + "uranium ore, which decides whether a scenario can be run at a location at "
     + "all — and even that goes through review before it changes anything.",
  },
  {
    q: "Who do I contact about my water?",
    a: "Your district groundwater office (Central Ground Water Board, Ranchi region) "
     + "and the Jharkhand State Pollution Control Board can advise on testing and, "
     + "where a supply is affected, on alternatives. This portal is an information "
     + "tool; it is not a regulator and cannot arrange testing for you.",
  },
];

export default function Methods() {
  const { me } = useAuth();
  const staff = isStaff(me?.role);

  // The engine's own register — technical, and shown only to staff. A citizen
  // reading "beta (dual-porosity capacity ratio) has no Singhbhum measurement
  // behind it" learns nothing they can use.
  const assumptions = useQuery({
    queryKey: ["ml", "assumptions"], enabled: staff, staleTime: 3_600_000,
    queryFn: () => api.get<any>("/ml/assumptions"),
  });

  return (
    <div className="page citizen">
      <div className="page-head">
        <h1>Data &amp; methods</h1>
        <p>
          What this platform knows, where it got it, and what it does not know.
        </p>
      </div>

      <div className="banner warn" style={{ marginBottom: "var(--s-5)" }}>
        <strong>No uranium in-situ recovery mine operates in Jharkhand.</strong> This is
        a screening and preparedness tool. It is not a permitting instrument and it
        does not report that anything has happened.
      </div>

      {PLAIN.map((item) => (
        <div className="card" key={item.q}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>{item.q}</div>
          <div className="prose muted">{item.a}</div>
        </div>
      ))}

      <div className="card">
        <div className="card-title">Where the data comes from</div>
        <TableScroll>
          <table className="grid">
            <thead>
              <tr><th>What</th><th>Source</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>Groundwater levels and quality</td>
                <td className="muted">Central Ground Water Board (CGWB), published monitoring network</td>
              </tr>
              <tr>
                <td>Aquifer maps and depth profiles</td>
                <td className="muted">CGWB NAQUIM district reports</td>
              </tr>
              <tr>
                <td>Uranium deposits and prospective belts</td>
                <td className="muted">IAEA UDEPO, Geological Survey of India</td>
              </tr>
              <tr>
                <td>Rivers and drainage</td>
                <td className="muted">HydroRIVERS v1.0</td>
              </tr>
              <tr>
                <td>District and block boundaries</td>
                <td className="muted">Government of Jharkhand administrative boundaries</td>
              </tr>
              <tr>
                <td>Contaminant behaviour in rock and water</td>
                <td className="muted">US EPA, IAEA and SKB published partition-coefficient studies</td>
              </tr>
              <tr>
                <td>Excursion screening rule</td>
                <td className="muted">Inspired by US NRC NUREG-1569 — structurally similar, not a licensed monitoring programme</td>
              </tr>
            </tbody>
          </table>
        </TableScroll>
      </div>

      {staff && (
        <div className="card">
          <div className="card-title">The engine's own assumption register</div>
          <div className="muted small" style={{ marginBottom: 10 }}>
            Technical, and staff-only — served live from the model's configuration so
            it cannot drift from what the model actually uses. Each entry is a value
            the model needs and does not have a local measurement for.
          </div>
          {assumptions.isLoading && <Loading />}
          {assumptions.data && (
            <TableScroll>
              <table className="grid">
                <thead>
                  <tr><th>Parameter</th><th>What is missing</th></tr>
                </thead>
                <tbody>
                  {Object.entries(assumptions.data as Record<string, any>)
                    .filter(([, v]) => typeof v === "string" || typeof v === "object")
                    .slice(0, 40)
                    .map(([k, v]) => (
                      <tr key={k}>
                        <td className="mono">{k}</td>
                        <td className="muted small">
                          {typeof v === "string" ? v : JSON.stringify(v).slice(0, 240)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </TableScroll>
          )}
        </div>
      )}

      <div className="muted small" style={{ marginTop: "var(--s-5)", lineHeight: "var(--lh-loose)" }}>
        Built at B.I.T. Sindri for the TEXMiN Mining CPS Centre of Excellence, as a
        research prototype for groundwater vulnerability assessment in mining regions.
      </div>
    </div>
  );
}
