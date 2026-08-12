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
import { api, type Observation } from "../api/client";
import { canReview, canSubmit, useAuth } from "../auth";
import { ErrorNote, Loading } from "../components/bits";

const TYPES = [
  { v: "ore_presence", label: "Uranium ore presence" },
  { v: "water_sample", label: "Water quality sample" },
  { v: "groundwater_level", label: "Groundwater level" },
];

function SubmitForm({ onDone }: { onDone: () => void }) {
  const [type, setType] = useState("ore_presence");
  const [f, setF] = useState<Record<string, string>>({
    name: "", longitude: "", latitude: "", ore_zone: "deposit",
    uranium_grade_pct: "", notes: "",
  });
  const set = (k: string, v: string) => setF({ ...f, [k]: v });

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
      throw new Error(
        "Only ore-presence submissions are wired into this form. Water-quality and " +
        "groundwater-level submissions need a well or station picker, which is not built yet.",
      );
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
        <div className="banner warn">
          <strong>Form not built for this type.</strong> The API accepts it, but a
          water-quality or level submission has to target an existing well or station,
          and that picker is not implemented. Ore presence is fully supported below.
        </div>
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
