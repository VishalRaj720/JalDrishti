import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type IsrPoint } from "../api/client";
import { canRunSims, useAuth } from "../auth";

interface RunSummary {
  id: string;
  status: string;
  species: string;
  created_at: string;
  runtime_ms: number | null;
  extrapolation: string[] | null;
  error_message: string | null;
}

export default function SiteRegistry() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<IsrPoint | null>(null);

  const sites = useQuery({
    queryKey: ["isr-points"],
    queryFn: () => api.get<IsrPoint[]>("/isr-points"),
  });

  const runs = useQuery({
    queryKey: ["runs", selected?.id],
    queryFn: () => api.get<RunSummary[]>(`/simulations/runs?isr_id=${selected!.id}`),
    enabled: !!selected,
    // Poll while the drawer is open. A run takes 5-15 s and finishes in a
    // background task, so without this the card sits on "running" forever.
    // A predicate over the query's own data was tried first and never fired —
    // one small GET every 3 s while a drawer is open is cheap, and there is
    // nothing subtle left to get wrong.
    refetchInterval: selected ? 3000 : false,
  });

  const trigger = useMutation({
    mutationFn: (id: string) =>
      api.post(`/simulations/${id}`, { species: "uranium_ppb", operation_years: 8, time_years: 20 }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs", selected?.id] }),
  });

  return (
    <>
      <div className="page">
        <h1>Site Registry</h1>
        <p className="lede">
          Hypothetical ISR sites. No such operation exists in Jharkhand — these are
          screening scenarios, and every simulation run is pinned to the model that
          produced it.
        </p>

        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="grid">
            <thead>
              <tr>
                <th>Name</th>
                <th>Coordinates</th>
                <th>Injection rate (m³/day)</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {sites.data?.map((s) => {
                const c = s.location?.coordinates;
                return (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 500 }}>{s.name}</td>
                    <td className="mono">
                      {c ? `${c[1].toFixed(4)}, ${c[0].toFixed(4)}` : "—"}
                    </td>
                    <td>{s.injection_rate ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="linkish" onClick={() => setSelected(s)}>
                        Open
                      </button>
                    </td>
                  </tr>
                );
              })}
              {sites.data?.length === 0 && (
                <tr>
                  <td colSpan={4} className="muted" style={{ padding: "var(--sp-5)" }}>
                    No sites registered.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <aside className="drawer">
          <div className="drawer-head">
            <div>
              <h2 style={{ margin: 0, fontSize: "var(--text-xl)" }}>{selected.name}</h2>
              <div className="muted">Hypothetical ISR site</div>
            </div>
            <button className="linkish" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>

          <div className="drawer-body">
            {canRunSims(me?.role) && (
              <button
                className="primary"
                style={{ width: "100%", marginBottom: "var(--sp-4)" }}
                disabled={trigger.isPending}
                onClick={() => trigger.mutate(selected.id)}
              >
                {trigger.isPending ? "Queueing…" : "Run simulation (uranium, 8 yr / 20 yr)"}
              </button>
            )}

            <div className="rail-section-label" style={{ padding: "0 0 var(--sp-2)" }}>
              Runs
            </div>

            {runs.isLoading && <div className="muted"><span className="spinner" /> Loading…</div>}
            {runs.data?.length === 0 && <div className="muted">No runs yet.</div>}

            {runs.data?.map((r) => (
              <div
                key={r.id}
                className="card"
                style={{ marginBottom: "var(--sp-3)", padding: "var(--sp-4)" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <strong>{r.species}</strong>
                  <span
                    className={`badge ${
                      r.status === "completed" ? "low" : r.status === "failed" ? "critical" : "medium"
                    }`}
                  >
                    {r.status}
                  </span>
                </div>
                <div className="muted" style={{ marginTop: 4 }}>
                  {new Date(r.created_at).toLocaleString()}
                  {r.runtime_ms ? ` · ${(r.runtime_ms / 1000).toFixed(1)}s` : ""}
                </div>

                {/* §4.5 rule 2 — extrapolation is loud. */}
                {r.extrapolation && r.extrapolation.length > 0 && (
                  <div className="notice" style={{ marginTop: "var(--sp-3)" }}>
                    <strong>Outside trained support:</strong>{" "}
                    <span className="mono">{r.extrapolation.join(", ")}</span>
                    <div style={{ marginTop: 4 }}>
                      The analytical engine is still valid here; the ML band is not
                      conformally guaranteed.
                    </div>
                  </div>
                )}
                {r.error_message && (
                  <div className="error" style={{ marginTop: "var(--sp-3)" }}>
                    {r.error_message}
                  </div>
                )}
              </div>
            ))}
          </div>
        </aside>
      )}
    </>
  );
}
