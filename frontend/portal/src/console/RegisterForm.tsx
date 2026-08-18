/**
 * Registering a pin as an ISR site — the full operating parameter set.
 *
 * WHAT THIS REPLACES, and why it is a correctness fix rather than a feature.
 * The old form was a name field and a button. It posted `injection_rate`, a key
 * the API does not have (it is `injection_rate_m3_day`), which Pydantic dropped
 * without complaint — so **every site registered through the portal took the
 * server's 2500 m³/day default**, whatever the analyst had set on the slider
 * beside it. The registry looked populated and was uniform by accident.
 *
 * Migration 0015 made a site a fully specified hypothetical operation precisely
 * so two people running "Jaduguda" run the same thing. This form is the half of
 * that intent the UI never delivered.
 *
 * RANGES COME FROM THE ENGINE, over `GET /ml/bounds` — never typed in here. A
 * bound hard-coded in a client is either a value the engine would have accepted
 * and the form refused, or a 422 the user cannot act on from a service they
 * have never heard of.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type EngineBounds, type IsrPoint } from "../api/client";
import { ErrorNote, Field } from "../components/bits";

/** One numeric parameter: which bounds keys describe it, and how to label it. */
interface ParamDef {
  key: keyof Payload;
  label: string;
  unit: string;
  /** Prefix of the `*_min` / `*_max` / `*_default` triple in `/ml/bounds`. */
  bounds: string;
  step: number;
  hint?: string;
}

interface Payload {
  injection_rate_m3_day: number;
  bleed_percent: number;
  operation_years: number;
  wellfield_width_m: number;
  monitor_ring_m: number;
  ore_depth_m: number;
  ore_thickness_m: number;
  restoration_years: number;
}

const PARAMS: ParamDef[] = [
  { key: "injection_rate_m3_day", label: "Injection rate", unit: "m³/day",
    bounds: "injection_rate", step: 50,
    hint: "Lixiviant delivered to the wellfield." },
  { key: "bleed_percent", label: "Bleed", unit: "%", bounds: "bleed", step: 0.1,
    hint: "Net over-extraction that holds the plume in. Its effect SATURATES — "
        + "past the bleed that first achieves full capture, raising it does nothing." },
  { key: "operation_years", label: "Operation duration", unit: "yr",
    bounds: "operation_years", step: 1,
    hint: "How long the operation injects. Fixed for the site; the evaluation "
        + "horizon is what a run varies." },
  { key: "wellfield_width_m", label: "Well-pattern footprint ⌀", unit: "m",
    bounds: "wellfield_width", step: 10,
    hint: "DIAMETER of the circular well-pattern footprint — the full transverse "
        + "extent of the wellfield. Not a borehole width and not a well spacing." },
  { key: "monitor_ring_m", label: "Monitor ring", unit: "m",
    bounds: "monitor_ring", step: 5,
    hint: "Perimeter monitoring distance from the wellfield EDGE. NUREG-1569 "
        + "records licensed rings at 75–180 m." },
  { key: "ore_depth_m", label: "Ore zone depth", unit: "m", bounds: "ore_depth", step: 5 },
  { key: "ore_thickness_m", label: "Ore zone thickness", unit: "m",
    bounds: "ore_thickness", step: 1 },
  { key: "restoration_years", label: "Restoration sweep (planned)", unit: "yr",
    bounds: "restoration", step: 1,
    hint: "0 = no remediation planned. A run can test a different sweep against "
        + "this site without editing it." },
];

export default function RegisterForm({
  lon, lat, onRegistered,
}: { lon: number; lat: number; onRegistered: (site: IsrPoint) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState("");
  const [touched, setTouched] = useState(false);

  const bounds = useQuery({
    queryKey: ["ml", "bounds"], staleTime: 3_600_000,
    queryFn: () => api.get<EngineBounds>("/ml/bounds"),
  });

  const B = bounds.data;
  const lim = (prefix: string) => {
    if (!B) return { min: 0, max: 0, def: 0 };
    // `restoration` and `horizon` carry a UI exploration max deliberately wider
    // than the trained one; the form offers the wider range and the run flags
    // the extrapolation rather than clamping a limitation out of sight.
    const max = B[`${prefix}_ui_max`] ?? B[`${prefix}_max`] ?? 0;
    return {
      min: B[`${prefix}_min`] ?? 0,
      max,
      def: B[`${prefix}_default`] ?? B[`${prefix}_min`] ?? 0,
    };
  };

  const [v, setV] = useState<Partial<Payload>>({});
  const value = (p: ParamDef): number => {
    const got = v[p.key];
    return got === undefined ? lim(p.bounds).def : got;
  };

  const errors = useMemo(() => {
    const e: Partial<Record<keyof Payload | "name", string>> = {};
    if (!name.trim()) e.name = "A site needs a name.";
    if (!B) return e;
    for (const p of PARAMS) {
      const { min, max } = lim(p.bounds);
      const n = value(p);
      if (!isFinite(n)) e[p.key] = "Enter a number.";
      else if (n < min || n > max) e[p.key] = `The engine accepts ${min}–${max} ${p.unit}.`;
    }
    return e;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, v, B]);

  const ok = Object.keys(errors).length === 0 && !!B;

  const register = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        name: name.trim(),
        location: { type: "Point", coordinates: [lon, lat] },
      };
      for (const p of PARAMS) body[p.key] = value(p);
      if (startDate) body.injection_start_date = new Date(startDate).toISOString();
      return api.post<IsrPoint>("/isr-points", body);
    },
    onSuccess: (site) => {
      qc.invalidateQueries({ queryKey: ["isr-points"] });
      onRegistered(site);
    },
  });

  return (
    <>
      <div className="sec">Register this location as a site</div>

      <div className="banner warn" style={{ marginBottom: 10 }}>
        A site is a <strong>fully specified hypothetical operation</strong>, not just a
        coordinate. Everything below is pinned to the site so that a run varies only
        the evaluation horizon and the restoration sweep — two people opening this site
        are then running the same thing.
      </div>

      <Field label="Site name" htmlFor="site-name" error={touched ? errors.name : null}
             hint="Include “(hypothetical)” if the name could be read as a real proposal.">
        <input id="site-name" value={name} onChange={(e) => setName(e.target.value)}
               placeholder="e.g. Bagjata North (hypothetical)"
               aria-invalid={touched && !!errors.name} />
      </Field>

      {bounds.isLoading && (
        <div className="muted small">Reading the engine's accepted ranges…</div>
      )}
      {bounds.error && (
        <div className="banner danger">
          Could not read the engine's parameter bounds, so this form cannot validate
          what you enter. Registration is disabled rather than guessing at ranges.
        </div>
      )}

      {B && PARAMS.map((p) => {
        const { min, max } = lim(p.bounds);
        const err = touched ? errors[p.key] : null;
        return (
          <Field key={p.key} label={`${p.label} (${p.unit})`} htmlFor={`p-${p.key}`}
                 error={err}
                 hint={<>{p.hint ? `${p.hint} ` : ""}<span className="mono">{min}–{max}</span></>}>
            <input id={`p-${p.key}`} type="number" step={p.step} min={min} max={max}
                   value={value(p)} aria-invalid={!!err}
                   onChange={(e) => setV({ ...v, [p.key]: Number(e.target.value) })} />
          </Field>
        );
      })}

      <Field label="Assumed start date — optional" htmlFor="p-start"
             hint="A presentation anchor only: it turns an evaluation year into a calendar
                   date and selects the seasonal water table. It does not make the run
                   historical — no ISR operation has taken place in Jharkhand.">
        <input id="p-start" type="date" value={startDate}
               onChange={(e) => setStartDate(e.target.value)} />
      </Field>

      <div className="muted small" style={{ marginBottom: 8 }}>
        Aquifer regime, hydraulic gradient and flow direction are deliberately left
        unset — the engine resolves them from its own datasets at this coordinate,
        which is more defensible than any value chosen here.
      </div>

      <button className="btn primary block" disabled={register.isPending}
              onClick={() => { setTouched(true); if (ok) register.mutate(); }}>
        {register.isPending ? "Registering…" : "Register site"}
      </button>
      {touched && !ok && !register.isPending && (
        <div className="muted small" style={{ marginTop: 6 }}>
          Fix the fields marked above to continue.
        </div>
      )}
      <ErrorNote error={register.error} />

      <div className="muted small" style={{ marginTop: 8 }}>
        Registering records a location to screen — not a proposal to mine it. The site
        becomes runnable here and, once a regulator publishes a screening for it,
        visible to residents of the blocks it affects.
      </div>
    </>
  );
}
