/**
 * Edit a registered site's operating parameters.
 *
 * WHY THIS EXISTS. `PUT /api/v1/isr-points/{id}` has always been implemented
 * and the 2026-08-24 audit found nothing in the portal called it. A site could
 * be created and destroyed but never corrected — so a mistyped injection rate
 * could only be fixed by deleting the site, which cascades and takes every
 * stored run and advisory filed against it with it. That is a destructive
 * workaround for a typo.
 *
 * WHY THE WARNING IS PROMINENT. Migration `0015` exists so that a site IS the
 * operation and two people running "Jaduguda" run the same thing. Editing these
 * numbers therefore changes what every FUTURE run computes, while stored runs
 * keep the values they were computed with. That is correct — a stored run is
 * immutable and pinned to its provenance — but it means the site's parameters
 * and an old run's parameters can legitimately disagree, and somebody comparing
 * them needs to know why. `Compare` reports it as an input delta.
 *
 * Bounds come from `GET /ml/bounds`, never retyped here: a limit hard-coded in
 * the client is a 422 the user cannot act on, from a service they never heard
 * of.
 */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type EngineBounds, type IsrPoint } from "../api/client";
import { ErrorNote } from "../components/bits";

type Field = {
  key: keyof IsrPoint;
  label: string;
  unit: string;
  /** Prefix of the `*_min` / `*_max` pair in the bounds map. */
  bounds?: string;
  /** Restoration is the one parameter whose max is not `<prefix>_max`: the
   *  engine publishes `restoration_trained_max` (10 yr, the envelope the
   *  surrogate was trained on) AND `restoration_ui_max` (30 yr, how far the
   *  analytical engine will still serve). The schema validates against the UI
   *  bound, so that is the one this form must show — using `_max` silently
   *  found nothing and rendered no range at all. */
  maxKey?: string;
  step?: number;
};

/** Mirrors RegisterForm's parameter list, minus the ones a site cannot change:
 *  location is fixed at registration (a site must not migrate across the map),
 *  and the identity fields are handled separately. */
const FIELDS: Field[] = [
  { key: "injection_rate_m3_day", label: "Injection rate", unit: "m³/day",
    bounds: "injection_rate", step: 50 },
  { key: "bleed_percent", label: "Bleed", unit: "%", bounds: "bleed", step: 0.1 },
  { key: "operation_years", label: "Operation duration", unit: "yr",
    bounds: "operation_years", step: 1 },
  { key: "restoration_years", label: "Restoration sweep (planned)", unit: "yr",
    bounds: "restoration", maxKey: "restoration_ui_max", step: 1 },
  { key: "wellfield_width_m", label: "Well-pattern footprint ⌀", unit: "m",
    bounds: "wellfield_width", step: 10 },
  { key: "monitor_ring_m", label: "Monitor ring", unit: "m",
    bounds: "monitor_ring", step: 10 },
  { key: "ore_depth_m", label: "Ore zone depth", unit: "m",
    bounds: "ore_depth", step: 5 },
  { key: "ore_thickness_m", label: "Ore zone thickness", unit: "m",
    bounds: "ore_thickness", step: 1 },
];

export default function SiteEditForm({
  site, bounds, onDone,
}: {
  site: IsrPoint;
  bounds: EngineBounds | undefined;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(site.name);
  const [vals, setVals] = useState<Record<string, string>>(() => {
    const v: Record<string, string> = {};
    for (const f of FIELDS) {
      const cur = site[f.key] as number | null;
      v[f.key as string] = cur === null || cur === undefined ? "" : String(cur);
    }
    return v;
  });

  const save = useMutation({
    mutationFn: () => {
      // Only send what changed. `IsrPointUpdate` is all-optional precisely so a
      // partial edit does not reset the rest to defaults, and sending the full
      // object would defeat that on any field the form does not render.
      const body: Record<string, unknown> = {};
      if (name.trim() && name !== site.name) body.name = name.trim();
      for (const f of FIELDS) {
        const raw = vals[f.key as string];
        if (raw === "") continue;
        const n = Number(raw);
        if (!Number.isFinite(n)) continue;
        if (n !== site[f.key]) body[f.key as string] = n;
      }
      return api.put<IsrPoint>(`/isr-points/${site.id}`, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["isr-points"] });
      qc.invalidateQueries({ queryKey: ["runs", site.id] });
      onDone();
    },
  });

  const dirty = name !== site.name || FIELDS.some(
    (f) => vals[f.key as string] !== (site[f.key] === null || site[f.key] === undefined
      ? "" : String(site[f.key])));

  return (
    <div className="card" style={{ margin: "8px 0" }}>
      <div className="row wrap" style={{ alignItems: "baseline" }}>
        <strong>Edit the operation</strong>
        <span className="spacer grow" />
        <button className="btn ghost small" onClick={onDone}>Cancel</button>
      </div>

      <p className="muted small" style={{ marginTop: 6 }}>
        These values are the operation. Changing them changes what every{" "}
        <em>future</em> run computes. Runs already stored keep the values they
        were computed with — they are immutable and pinned to their provenance —
        so an old run and this site can legitimately disagree afterwards.
      </p>

      <label>
        <div className="muted small">Site name</div>
        <input type="text" value={name} maxLength={200}
               onChange={(e) => setName(e.target.value)} />
      </label>

      {FIELDS.map((f) => {
        const min = f.bounds ? bounds?.[`${f.bounds}_min`] : undefined;
        const max = f.bounds
          ? bounds?.[f.maxKey ?? `${f.bounds}_max`]
          : undefined;
        return (
          <label key={String(f.key)} style={{ display: "block", marginTop: 6 }}>
            <div className="muted small">
              {f.label} <span style={{ opacity: 0.7 }}>({f.unit})</span>
              {min !== undefined && max !== undefined && (
                <span style={{ opacity: 0.6 }}> · {min}–{max}</span>
              )}
            </div>
            <input
              type="number" step={f.step} min={min} max={max}
              value={vals[f.key as string]}
              onChange={(e) => setVals({ ...vals, [f.key as string]: e.target.value })}
            />
          </label>
        );
      })}

      <ErrorNote error={save.error} />

      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn" disabled={!dirty || save.isPending}
                onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save changes"}
        </button>
        {!dirty && <span className="muted small">Nothing changed yet.</span>}
      </div>
    </div>
  );
}
