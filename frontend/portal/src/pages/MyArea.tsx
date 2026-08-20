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
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  api, type MyArea as MyAreaData, type PublicAdvisory, type Subscription,
} from "../api/client";
import { Empty, ErrorNote, Loading, RiskBand } from "../components/bits";

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

  return (
    <div className="page citizen">
      <div className="page-head">
        <h1>Groundwater near you</h1>
        <p>
          Real test results from government groundwater sampling across Jharkhand,
          for the areas you follow.
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
        <div className="card" key={b.id}>
          <div className="row wrap">
            <div>
              <strong style={{ fontSize: "var(--fs-lg)" }}>{b.name}</strong>
              <div className="muted small">{b.district ?? ""}</div>
            </div>
            <span className="spacer grow" />
            <RiskBand label={b.band} />
          </div>

          <div className="prose" style={{ marginTop: 10 }}>{b.what_it_means}</div>

          <div className="muted small" style={{ marginTop: 10 }}>
            {b.wells} well{b.wells === 1 ? "" : "s"} tested
            {b.samples > 0 && ` · ${b.samples} sample${b.samples === 1 ? "" : "s"}`}
            {b.last_sampled &&
              ` · last tested ${new Date(b.last_sampled).toLocaleDateString()}`}
          </div>

          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn ghost" onClick={() => remove.mutate(b.id)}>
              Stop following
            </button>
          </div>
        </div>
      ))}

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
          <h2 style={{ fontSize: "var(--fs-lg)", marginTop: "var(--s-6)" }}>
            Assessments published for your area
          </h2>
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
