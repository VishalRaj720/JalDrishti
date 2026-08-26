/**
 * "My Area" — the citizen's home screen.
 *
 * Before P5 a citizen got a district dropdown, a table of readings, and a card
 * saying alerts were planned. This is the screen the proposal actually
 * describes: choose where you live, see what was measured there, and be told
 * when something changes.
 *
 * COPY RULES, applied throughout and not negotiable per-component:
 *   · measured results come FIRST, always — what was actually tested in your
 *     water matters more than what was modelled, and order is a claim about
 *     importance whether or not it is meant to be
 *   · "No data" is drawn as a MONITORING GAP, never as a clean result
 *   · no P10/P90, no species codes, no `conformal`, no `Domenico`
 *   · the hypothetical premise appears in the first paragraph of anything
 *     model-derived, not in a footnote
 *
 * ── R15 RESTRUCTURE ──
 *
 * The screen was a stack of identical cards, so the verdict — the one thing a
 * resident opens this for — was a small chip in the corner of the first one,
 * the same size as the "Stop following" button. It is now the largest element
 * on the page, and the evidence sits beneath it rather than around it.
 *
 * The reading is drawn against the limit rather than stated beside it. "18.4
 * ppb" requires the reader to already know that 30 is the limit; a scale with
 * the limit marked on it does not. That component is shared with the staff
 * water-quality screen, so the two surfaces cannot drift apart in how they
 * judge the same number.
 *
 * THE URANIUM-ONLY VERDICT IS GONE, AND SO IS THE CAVEAT THAT APOLOGISED FOR IT.
 * `GET /citizen/my-area` used to band a block on uranium alone while the public
 * map banded on uranium, nitrate and fluoride — two citizen surfaces, two rules,
 * one product, so a block could read "Low concern" here and "High concern" on
 * the map, both correct. The first cut of this screen could only state which
 * determinand its verdict rested on and point at the map. The API was fixed on
 * 2026-08-26 (`services/health_bands.py`), so the verdict now IS the map's
 * verdict and the three determinands behind it are drawn out individually.
 *
 * The limits are read from the response rather than written here. A threshold
 * duplicated in the client is the same defect one layer up.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  api, type HealthLimits, type MyArea as MyAreaData, type MyAreaBlock,
  type PublicAdvisory, type Subscription, type WqStatus,
} from "../api/client";
import { Empty, ErrorNote, Loading } from "../components/bits";
import {
  DeterminandScale, Freshness, Readout, SectionHead, Verdict,
} from "../components/instruments";

function BlockPicker({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [q, setQ] = useState("");

  const results = useQuery({
    queryKey: ["citizen-blocks", q],
    queryFn: () => api.get<Array<{ id: string; name: string; district: string | null }>>(
      `/citizen/blocks?q=${encodeURIComponent(q)}&limit=30`),
  });

  const add = useMutation({
    mutationFn: (block_id: string) => api.post("/citizen/subscriptions", { block_id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-area"] });
      qc.invalidateQueries({ queryKey: ["citizen-subs"] });
      onDone();
    },
  });

  return (
    <div className="card">
      <div className="card-title">Find your area</div>
      <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus
             placeholder="Type your block or district name…"
             aria-label="Search for your block" />
      <div className="muted small" style={{ margin: "8px 0" }}>
        Choose the <strong>block</strong> you live in. Blocks are the smallest areas
        this data covers — there is no village-level groundwater dataset available,
        so we do not pretend to offer one.
      </div>
      {results.isLoading && <Loading />}
      {results.data?.length === 0 && (
        <div className="muted small">No block matches “{q}”.</div>
      )}
      {results.data?.map((b) => (
        <button key={b.id} className="list-item" onClick={() => add.mutate(b.id)}>
          <div>
            <div className="nm">{b.name}</div>
            <div className="mt">{b.district ?? ""}</div>
          </div>
          <span className="chip info">Follow</span>
        </button>
      ))}
      <ErrorNote error={add.error} />
    </div>
  );
}

/**
 * A determinand's status under IS 10500, for one measured maximum.
 *
 * Uranium and nitrate carry NO RELAXATION, so there is no tolerated band above
 * their limit and a reading at or over it goes straight to `above_permissible`.
 * Only fluoride has a real middle band. Inventing an amber zone for the other
 * two would misstate the standard in the reassuring direction.
 */
function statusOf(
  v: number | null | undefined, acceptable: number, permissible: number | null,
): WqStatus {
  if (v === null || v === undefined) return "not_tested";
  if (permissible !== null) {
    if (v > permissible) return "above_permissible";
    if (v > acceptable) return "above_acceptable";
    return "acceptable";
  }
  return v >= acceptable ? "above_permissible" : "acceptable";
}

/** IS 10500's vocabulary, said the way a resident would say it.
 *  "Above permissible" is a regulator's phrase; this screen is not for them. */
const PLAIN: Record<WqStatus, { text: string; cls: string }> = {
  above_permissible: { text: "Above the safe limit", cls: "danger" },
  above_acceptable: { text: "Above the preferred level", cls: "warn" },
  acceptable: { text: "Within the safe limit", cls: "ok" },
  no_limit: { text: "No limit set", cls: "neutral" },
  not_tested: { text: "Not tested here", cls: "neutral" },
};

/**
 * The three determinands this surface is banded on, drawn against their limits.
 *
 * WHY THREE AND NOT ONE. Until 2026-08-26 this screen showed uranium alone,
 * because the API banded on uranium alone. Both now read uranium, nitrate and
 * fluoride, which is the only reason a resident of a block over the fluoride
 * limit is told so here rather than only on the map.
 *
 * The scales carry per-substance statuses, NOT the block's band. Those answer
 * different questions — "is this substance over its limit" versus "how
 * concerning is this block overall" — and the verdict above already says which
 * substance set the band, in words, from the server. An earlier draft put the
 * band on the scale as its chip and produced a contradiction the moment the
 * band came from a determinand the scale was not showing.
 */
function BlockCard({
  b, limits, onUnfollow, unfollowing,
}: {
  b: MyAreaBlock; limits: HealthLimits;
  onUnfollow: () => void; unfollowing: boolean;
}) {
  // ABSENT AND NULL MEAN DIFFERENT THINGS HERE, and conflating them would
  // reintroduce this product's central error pointing the other way.
  //
  // `null` is a real finding: the server looked, and nothing in this block was
  // analysed for that substance. `undefined` means the SERVER never mentioned
  // it — which is exactly what an older API returns, and is true of the
  // deployed one until the backend fix ships alongside this bundle. Rendering
  // "Not tested here" for a field the response simply does not carry would
  // invent a monitoring gap, and a fabricated gap is a false statement even
  // when it errs toward caution.
  const has = (v: number | null | undefined) => v !== undefined;
  const scales = [
    {
      key: "uranium", label: "Uranium", unit: "ppb",
      value: b.max_uranium_ppb,
      acceptable: limits.uranium_ppb, permissible: null,
      relaxation: "no relaxation is permitted above this limit",
    },
    ...(has(b.max_nitrate_mg_l) ? [{
      key: "nitrate", label: "Nitrate", unit: "mg/L",
      value: b.max_nitrate_mg_l ?? null,
      acceptable: limits.nitrate_mg_l, permissible: null,
      relaxation: "no relaxation is permitted above this limit",
    }] : []),
    ...(has(b.max_fluoride_mg_l) ? [{
      key: "fluoride", label: "Fluoride", unit: "mg/L",
      value: b.max_fluoride_mg_l ?? null,
      acceptable: limits.fluoride_acceptable_mg_l,
      permissible: limits.fluoride_mg_l,
      relaxation: "the higher mark is tolerated only where there is no other source",
    }] : []),
  ];

  return (
    <div style={{ marginBottom: "var(--s-5)" }}>
      <Verdict band={b.band} place={b.name} district={b.district}
               say={b.what_it_means}>
        <Readout label="Wells tested" value={b.wells}
                 tone={b.wells ? undefined : "gap"} />
        <Readout label="Samples" value={b.samples}
                 tone={b.samples ? undefined : "gap"} />
        <Readout
          label="Most recent test"
          value={<Freshness at={b.last_sampled} prefix="" />}
        />
      </Verdict>

      <div className="card">
        <div className="card-title">
          What was measured, against the safe limits
          {b.band_driver && (
            <>
              <span className="spacer grow" />
              <span className="chip warn">
                {b.band_driver} set this area’s rating
              </span>
            </>
          )}
        </div>
        {scales.map((s) => {
          const st = statusOf(s.value, s.acceptable, s.permissible);
          const plain = PLAIN[st];
          return (
            <DeterminandScale
              key={s.key}
              label={`${s.label} — highest reading from a tested well here`}
              unit={s.unit}
              value={s.value}
              status={st}
              acceptable={s.acceptable}
              permissible={s.permissible}
              range={null}
              relaxation={s.relaxation}
              statusChip={<span className={`chip ${plain.cls}`}>{plain.text}</span>}
              gapNote={
                b.samples > 0
                  ? `Samples from this block exist, but none was analysed for ${s.label.toLowerCase()}. Nothing here can tell you about it either way — that is a gap in testing, not a clean result.`
                  : "No groundwater sample from this block is in the government dataset. That is a gap in monitoring — it is not a clean result."
              }
            />
          );
        })}

        {(b.untested_health?.length ?? 0) > 0 && (
          <div className="banner warn" style={{ marginTop: "var(--s-4)" }}>
            <strong>Not everything was tested here.</strong> No result for{" "}
            {b.untested_health!.join(", ")}. A substance nobody measured has not
            been shown to be safe.
          </div>
        )}

        <div className="row wrap" style={{ marginTop: "var(--s-3)" }}>
          <button className="btn ghost" onClick={onUnfollow} disabled={unfollowing}>
            Stop following {b.name}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function MyArea() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [picking, setPicking] = useState(false);

  const area = useQuery({
    queryKey: ["my-area"], queryFn: () => api.get<MyAreaData>("/citizen/my-area"),
  });
  const advisories = useQuery({
    queryKey: ["citizen-advisories"],
    queryFn: () => api.get<PublicAdvisory[]>("/citizen/advisories?mine_only=true"),
  });
  const subs = useQuery({
    queryKey: ["citizen-subs"],
    queryFn: () => api.get<Subscription[]>("/citizen/subscriptions"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.del(`/citizen/subscriptions/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-area"] });
      qc.invalidateQueries({ queryKey: ["citizen-subs"] });
    },
  });

  const blocks = area.data?.blocks ?? [];
  // Limits come from the server so the portal never carries a second copy of a
  // threshold. The fallbacks are the IS 10500 values and exist only so an
  // in-flight response cannot blank the scales.
  const limits: HealthLimits = area.data?.limits ?? {
    uranium_ppb: area.data?.safe_limit_ppb ?? 30,
    nitrate_mg_l: 45,
    fluoride_mg_l: 1.5,
    fluoride_acceptable_mg_l: 1.0,
  };

  return (
    <div className="page citizen">
      <div className="page-head">
        <h1>Groundwater near you</h1>
        <p>
          Real test results from government groundwater sampling across Jharkhand,
          for the areas you follow. These are measurements, not predictions.
        </p>
      </div>

      {area.isLoading && <Loading label="Loading your area…" />}
      <ErrorNote error={area.error} />

      {!area.isLoading && blocks.length === 0 && !picking && (
        <div className="card">
          <div className="card-title">Choose where you live</div>
          <div className="prose muted" style={{ marginBottom: 12 }}>
            Follow your block to see what has been measured in its groundwater, and
            to be told when something changes.
          </div>
          <button className="btn primary lg" onClick={() => setPicking(true)}>
            Find my area
          </button>
        </div>
      )}

      {picking && <BlockPicker onDone={() => setPicking(false)} />}

      {/* ── MEASURED FIRST. This is real, and it is about water people drink. ── */}
      {blocks.map((b) => (
        <BlockCard
          key={b.id}
          b={b}
          limits={limits}
          unfollowing={remove.isPending}
          onUnfollow={() => remove.mutate(b.id)}
        />
      ))}
      <ErrorNote error={remove.error} />

      {blocks.length > 0 && !picking && (
        <button className="btn" onClick={() => setPicking(true)}>
          Follow another area
        </button>
      )}

      {blocks.length > 0 && (
        <div className="banner" style={{ marginTop: 14 }}>
          {area.data?.what_this_is}
        </div>
      )}

      {/* ── SCREENINGS SECOND, and clearly marked as models. ── */}
      {(advisories.data?.length ?? 0) > 0 && (
        <>
          <SectionHead title="Assessments published for your area">
            These are modelled scenarios, not measurements — a different kind of
            statement from everything above.
          </SectionHead>
          <div className="banner warn" style={{ marginBottom: 12 }}>
            {advisories.data![0].what_this_is}
          </div>
          {advisories.data!.map((a) => (
            <div className="card" key={a.id}>
              <div className="row wrap">
                <strong>{a.headline}</strong>
                <span className="spacer grow" />
                <span className="chip warn">Assessment</span>
              </div>
              <div className="prose" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                {a.what_it_means}
              </div>
              {a.what_to_do && (
                <div className="prose" style={{ marginTop: 10 }}>
                  <strong>What to do:</strong> {a.what_to_do}
                </div>
              )}
              <div className="muted small" style={{ marginTop: 10 }}>
                {a.published_at &&
                  `Published ${new Date(a.published_at).toLocaleDateString()}`}
                {a.blocks.length > 0 &&
                  ` · covers about ${a.blocks[0].overlap_ha.toFixed(1)} hectares of ${a.blocks[0].name}`}
              </div>
            </div>
          ))}
        </>
      )}

      {blocks.length > 0 && (
        <div className="card" style={{ marginTop: "var(--s-5)" }}>
          <div className="card-title">
            Alerts
            <span className="spacer grow" />
            {(area.data?.unread ?? 0) > 0 && (
              <span className="chip danger">{area.data!.unread} unread</span>
            )}
          </div>
          <div className="prose muted" style={{ marginBottom: 10 }}>
            You are told here when a well near you tests above the safe limit, and when
            an assessment is published for your area. Alerts appear in this portal only
            — we do not send SMS or email.
          </div>
          <button className="btn primary" onClick={() => nav("/alerts")}>
            Open my alerts
          </button>
        </div>
      )}

      {subs.data && subs.data.length > 0 && (
        <div className="muted small" style={{ marginTop: "var(--s-4)" }}>
          Following {subs.data.length} area{subs.data.length === 1 ? "" : "s"}. Only you
          can see which areas you follow.
        </div>
      )}

      {!area.isLoading && blocks.length === 0 && picking === false && (
        <Empty>
          Nothing to show yet — follow an area above and its test results will appear
          here.
        </Empty>
      )}
    </div>
  );
}
