/**
 * Field Data — one screen, two jobs, decided by role.
 *
 * A field officer submits and tracks their own work; a reviewer decides on
 * everyone's. They share a screen because they share a subject, but the
 * capabilities are strictly separated: the submit form is invisible to a
 * reviewer who cannot submit, and the decision buttons are invisible to an
 * officer who cannot approve. Both are enforced again by the API, and the
 * "cannot review your own" rule is a database CHECK constraint.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Observation, type TargetList } from "../api/client";
import { canReview, canSubmit, useAuth } from "../auth";
import { ErrorNote, Loading } from "../components/bits";

const TYPES = [
  { v: "ore_presence", label: "Uranium ore presence" },
  { v: "water_sample", label: "Water quality sample" },
  { v: "groundwater_level", label: "Groundwater level" },
];

/** The chemistry a field officer may record, matching `ALLOWED_FIELDS` on the
 *  backend. Uranium leads because it is the contaminant this platform screens
 *  for and the one most often left unmeasured. */
const CHEM_FIELDS = [
  { k: "uranium_ppb", label: "Uranium (ppb)" },
  { k: "ph", label: "pH" },
  { k: "ec_us_cm", label: "EC (µS/cm)" },
  { k: "tds_mg_l", label: "TDS (mg/L)" },
  { k: "sulphate_mg_l", label: "Sulphate (mg/L)" },
  { k: "chloride_mg_l", label: "Chloride (mg/L)" },
  { k: "nitrate_mg_l", label: "Nitrate (mg/L)" },
  { k: "fluoride_mg_l", label: "Fluoride (mg/L)" },
  { k: "total_hardness", label: "Total hardness" },
  { k: "iron_ppm", label: "Iron (ppm)" },
  { k: "arsenic_ppb", label: "Arsenic (ppb)" },
  { k: "bicarbonate_mg_l", label: "Bicarbonate (mg/L)" },
];

function SubmitForm({ onDone }: { onDone: () => void }) {
  const [type, setType] = useState("ore_presence");
  const [f, setF] = useState<Record<string, string>>({
    name: "", longitude: "", latitude: "", ore_zone: "deposit",
    uranium_grade_pct: "", notes: "",
    target_id: "", sampled_at: "", recorded_at: "", groundwater_level: "",
  });
  const set = (k: string, v: string) => setF({ ...f, [k]: v });
  const [targetQ, setTargetQ] = useState("");

  /** The wells or stations this submission can attach to. */
  const targets = useQuery({
    queryKey: ["obs-targets", type, targetQ],
    enabled: type !== "ore_presence",
    queryFn: () => api.get<TargetList>(
      `/field-observations/targets?observation_type=${type}`
      + (targetQ ? `&q=${encodeURIComponent(targetQ)}` : "")),
  });
  const chosen = targets.data?.items.find((t) => t.id === f.target_id);

  const submit = useMutation({
    mutationFn: () => {
      const now = new Date().toISOString();
      if (type === "ore_presence") {
        return api.post("/field-observations", {
          observation_type: "ore_presence", operation: "create", note: f.notes || null,
          payload: {
            name: f.name, longitude: Number(f.longitude), latitude: Number(f.latitude),
            ore_zone: f.ore_zone, observed_at: now,
            ...(f.uranium_grade_pct ? { uranium_grade_pct: Number(f.uranium_grade_pct) } : {}),
            ...(f.notes ? { notes: f.notes } : {}),
          },
        });
      }
      if (!f.target_id) {
        throw new Error(
          type === "water_sample"
            ? "Choose the monitoring well this sample came from."
            : "Choose the monitoring station this reading came from.");
      }

      if (type === "water_sample") {
        // Only the fields actually filled in are sent. A blank chemistry box
        // must NOT become 0 — a zero is a measurement, and inventing one turns
        // "we did not test for this" into "we tested and found none", which is
        // the exact confusion the rest of this product works to prevent.
        const chem: Record<string, number> = {};
        for (const k of CHEM_FIELDS.map((c) => c.k)) {
          if (f[k] !== undefined && f[k] !== "") chem[k] = Number(f[k]);
        }
        return api.post("/field-observations", {
          observation_type: "water_sample", operation: "create",
          note: f.notes || null,
          payload: {
            well_id: f.target_id,
            sampled_at: f.sampled_at ? new Date(f.sampled_at).toISOString() : now,
            ...chem,
          },
        });
      }

      return api.post("/field-observations", {
        observation_type: "groundwater_level", operation: "create",
        note: f.notes || null,
        payload: {
          station_id: f.target_id,
          recorded_at: f.recorded_at ? new Date(f.recorded_at).toISOString() : now,
          groundwater_level: Number(f.groundwater_level),
        },
      });
    },
    onSuccess: onDone,
  });

  return (
    <div className="card">
      <div className="card-title">Submit a field observation</div>

      <div className="seg" style={{ marginBottom: 11 }}>
        {TYPES.map((t) => (
          <button key={t.v} className={type === t.v ? "active" : ""} onClick={() => setType(t.v)}>
            {t.label}
          </button>
        ))}
      </div>

      {type !== "ore_presence" ? (
        <>
          {/* The picker that was missing. A sample belongs to a well and a level
              reading to a station; neither can be submitted without one. */}
          <div className="field">
            <label>
              {type === "water_sample" ? "Monitoring well" : "Monitoring station"}
            </label>
            <input placeholder="Search by name or district…" value={targetQ}
              onChange={(e) => setTargetQ(e.target.value)} />
            <select value={f.target_id} onChange={(e) => set("target_id", e.target.value)}
              style={{ marginTop: 6 }}>
              <option value="">
                {targets.isLoading ? "Loading…"
                  : `${targets.data?.count ?? 0} available — choose one…`}
              </option>
              {(targets.data?.items ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}{t.district ? ` · ${t.district}` : ""}
                  {t.last_sampled
                    ? ` · last ${new Date(t.last_sampled).getFullYear()}`
                    : " · never sampled"}
                </option>
              ))}
            </select>
            {chosen && (
              <div className="muted small" style={{ marginTop: 4 }}>
                {chosen.latitude?.toFixed(4)}, {chosen.longitude?.toFixed(4)}
                {" · "}{chosen.samples} previous reading(s)
                {type === "water_sample" && (
                  chosen.uranium_tests === 0
                    ? <b className="warn-text"> · never analysed for uranium</b>
                    : ` · ${chosen.uranium_tests} uranium result(s)`
                )}
              </div>
            )}
          </div>

          {type === "water_sample" ? (
            <>
              <div className="field">
                <label>Sampled at</label>
                <input type="datetime-local" value={f.sampled_at}
                  onChange={(e) => set("sampled_at", e.target.value)} />
              </div>
              <div className="muted small" style={{ margin: "4px 0 8px" }}>
                Fill in only what was actually measured. <b>A blank box is left
                blank</b> — it is not recorded as zero, because "not tested" and
                "tested and found none" are different findings.
              </div>
              <div className="grid-2">
                {CHEM_FIELDS.map((c) => (
                  <div className="field" key={c.k}>
                    <label>{c.label}</label>
                    <input type="number" step="any" value={f[c.k] ?? ""}
                      placeholder="not measured"
                      onChange={(e) => set(c.k, e.target.value)} />
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="grid-2">
              <div className="field">
                <label>Recorded at</label>
                <input type="datetime-local" value={f.recorded_at}
                  onChange={(e) => set("recorded_at", e.target.value)} />
              </div>
              <div className="field">
                <label>Groundwater level (m below ground)</label>
                <input type="number" step="any" value={f.groundwater_level}
                  placeholder="e.g. 3.5"
                  onChange={(e) => set("groundwater_level", e.target.value)} />
              </div>
            </div>
          )}

          <div className="field">
            <label>Notes for the reviewer</label>
            <textarea rows={2} value={f.notes}
              onChange={(e) => set("notes", e.target.value)} />
          </div>

          <div className="muted small">
            Submitted observations are <b>proposals</b>. An admin reviews each one,
            and only a sync carries an approved row into the datasets the engine
            reads — visible on the Dataset manager.
          </div>
        </>
      ) : (
        <>
          <div className="grid-2">
            <div className="field">
              <label>Deposit / outcrop name</label>
              <input value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Bagjata East outcrop" />
            </div>
            <div className="field">
              <label>Ore zone</label>
              <select value={f.ore_zone} onChange={(e) => set("ore_zone", e.target.value)}>
                <option value="deposit">deposit</option>
                <option value="belt">belt</option>
                <option value="none">none</option>
              </select>
            </div>
            <div className="field">
              <label>Longitude (°E)</label>
              <input value={f.longitude} onChange={(e) => set("longitude", e.target.value)} placeholder="86.36" />
            </div>
            <div className="field">
              <label>Latitude (°N)</label>
              <input value={f.latitude} onChange={(e) => set("latitude", e.target.value)} placeholder="22.65" />
            </div>
            <div className="field">
              <label>Uranium grade (%) — optional</label>
              <input value={f.uranium_grade_pct} onChange={(e) => set("uranium_grade_pct", e.target.value)} placeholder="0.05" />
            </div>
            <div className="field">
              <label>Field notes</label>
              <input value={f.notes} onChange={(e) => set("notes", e.target.value)} placeholder="what you saw" />
            </div>
          </div>

          <button className="btn primary" disabled={!f.name || !f.longitude || !f.latitude || submit.isPending}
                  onClick={() => submit.mutate()}>
            {submit.isPending ? "Submitting…" : "Submit for review"}
          </button>
          <ErrorNote error={submit.error} />
          <div className="muted small" style={{ marginTop: 8 }}>
            This enters a <strong>pending</strong> state. It changes nothing until a
            regulator or administrator approves it, and even then it reaches the
            simulation engine only after a dataset sync.
          </div>
        </>
      )}
    </div>
  );
}

function Diff({ o }: { o: Observation }) {
  return (
    <div className="grid-2" style={{ marginTop: 11 }}>
      <div>
        <div className="muted small" style={{ marginBottom: 4 }}>Current</div>
        <pre className="mono" style={{ margin: 0, whiteSpace: "pre-wrap", color: "var(--muted)" }}>
          {o.previous ? JSON.stringify(o.previous, null, 1) : "— new record —"}
        </pre>
      </div>
      <div>
        <div className="muted small" style={{ marginBottom: 4 }}>Proposed</div>
        <pre className="mono" style={{ margin: 0, whiteSpace: "pre-wrap", color: "var(--ok)" }}>
          {o.proposed ? JSON.stringify(o.proposed, null, 1) : "— deletion —"}
        </pre>
      </div>
    </div>
  );
}

export default function FieldData() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const reviewer = canReview(me?.role);

  // RLS scopes this: a field officer receives only their own submissions, so
  // there is no client-side filter to forget.
  const all = useQuery({
    queryKey: ["obs", "all"],
    queryFn: () => api.get<Observation[]>("/field-observations?limit=200"),
  });

  const decide = useMutation({
    mutationFn: ({ id, verb }: { id: string; verb: "approve" | "reject" }) =>
      api.post(`/field-observations/${id}/${verb}`, { review_note: note || null }),
    onSuccess: () => {
      setNote("");
      ["obs", "sync-status", "obs-map"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
  });

  const withdraw = useMutation({
    mutationFn: (id: string) => api.post(`/field-observations/${id}/withdraw`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["obs"] }),
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ["obs"] });
  const pending = (all.data ?? []).filter((o) => o.status === "pending");
  const decided = (all.data ?? []).filter((o) => o.status !== "pending");

  return (
    <div className="page">
      <div className="page-head">
        <h1>Field Data</h1>
        <p>
          {reviewer
            ? "Evidence submitted from the field. Approving makes it authoritative in the portal; it reaches the simulation engine only after a dataset sync."
            : "Your submissions. Nothing you send changes the record until a reviewer accepts it."}
        </p>
      </div>

      {canSubmit(me?.role) && <SubmitForm onDone={refresh} />}

      <div className="card">
        <div className="card-title">
          🔴 Awaiting review
          <span className="spacer grow" />
          <span className="chip danger">{pending.length}</span>
        </div>
        {all.isLoading && <Loading />}
        {pending.length === 0 && <div className="muted small">Nothing awaiting review.</div>}

        {pending.map((o) => (
          <div key={o.id} className="card" style={{ background: "var(--card2)" }}>
            <div className="row">
              <div>
                <strong>{o.operation} · {o.observation_type.replace(/_/g, " ")}</strong>
                <div className="muted small">
                  into <span className="mono">{o.target_table}</span> ·{" "}
                  {new Date(o.submitted_at).toLocaleString()}
                  {o.note ? ` · “${o.note}”` : ""}
                </div>
              </div>
              <span className="spacer grow" />
              {reviewer ? (
                <div className="row">
                  <button className="btn primary" disabled={decide.isPending}
                          onClick={() => decide.mutate({ id: o.id, verb: "approve" })}>Approve</button>
                  <button className="btn danger" disabled={decide.isPending}
                          onClick={() => decide.mutate({ id: o.id, verb: "reject" })}>Reject</button>
                </div>
              ) : (
                <button className="btn ghost" onClick={() => withdraw.mutate(o.id)}>Withdraw</button>
              )}
            </div>
            <Diff o={o} />
          </div>
        ))}

        {reviewer && pending.length > 0 && (
          <div className="field" style={{ marginTop: 9 }}>
            <label>Decision note (optional — recorded in the audit trail)</label>
            <input value={note} onChange={(e) => setNote(e.target.value)}
                   placeholder="why you approved or rejected" />
          </div>
        )}
        <ErrorNote error={decide.error} />
      </div>

      <div className="card">
        <div className="card-title">Decided</div>
        {decided.length === 0 && <div className="muted small">Nothing decided yet.</div>}
        <table className="grid">
          <tbody>
            {decided.map((o) => (
              <tr key={o.id}>
                <td>{o.observation_type.replace(/_/g, " ")}</td>
                <td className="muted">{new Date(o.submitted_at).toLocaleDateString()}</td>
                <td className="muted small">{o.review_note ?? ""}</td>
                <td>
                  {o.status === "approved" ? (
                    <span className="chip ok">approved</span>
                  ) : o.status === "rejected" ? (
                    <span className="chip danger">rejected</span>
                  ) : (
                    <span className="chip neutral">{o.status}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
