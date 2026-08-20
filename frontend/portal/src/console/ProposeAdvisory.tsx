/**
 * Proposing a completed run for publication.
 *
 * The analyst writes what a resident would read; an admin decides whether it
 * is published. That split is the point — an analyst dropping a pin should not
 * be able to send a notification to everyone in a block.
 *
 * TWO THINGS THIS SCREEN REFUSES TO LET THE AUTHOR GET WRONG:
 *
 * 1. **The reach is shown before the words are written.** The footprint and the
 *    blocks it actually intersects are computed server-side and displayed here,
 *    so the author is describing a real extent rather than an impression of one.
 *    A ~13 ha footprint against a ~30,000 ha block is the normal case, and it
 *    is stated in those terms.
 * 2. **The hypothetical premise is appended server-side** and cannot be edited
 *    away. It is not a checkbox the author might miss.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Advisory, type SimRun } from "../api/client";
import { canAdmin, useAuth } from "../auth";
import { ErrorNote, Field } from "../components/bits";
import { fmt } from "./mapLayers";

export default function ProposeAdvisory({ run }: { run: SimRun }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [headline, setHeadline] = useState("");
  const [meaning, setMeaning] = useState("");
  const [todo, setTodo] = useState("");

  const existing = useQuery({
    queryKey: ["advisories", "run", run.id],
    queryFn: () => api.get<Advisory[]>(`/advisories?isr_point_id=${run.isr_point_id}`),
  });
  const forThisRun = (existing.data ?? []).filter((a) => a.run_id === run.id);

  const propose = useMutation({
    mutationFn: () => api.post<Advisory>("/advisories", {
      run_id: run.id, headline: headline.trim(),
      what_it_means: meaning.trim(),
      what_to_do: todo.trim() || null,
    }),
    onSuccess: () => {
      setOpen(false); setHeadline(""); setMeaning(""); setTodo("");
      qc.invalidateQueries({ queryKey: ["advisories"] });
    },
  });

  const ok = headline.trim().length >= 8 && meaning.trim().length >= 20;

  if (run.status !== "completed") return null;

  return (
    <>
      <div className="sec">Publication</div>

      {forThisRun.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {forThisRun.map((a) => (
            <div key={a.id} className="readonly-val" style={{ marginBottom: 5 }}>
              <span className="muted small">{a.headline.slice(0, 40)}…</span>
              <span className={`chip ${
                a.status === "published" ? "ok"
                  : a.status === "proposed" ? "warn"
                  : a.status === "withdrawn" ? "danger" : "neutral"}`}>
                {a.status}
              </span>
            </div>
          ))}
        </div>
      )}

      {!open ? (
        <button className="btn block" onClick={() => setOpen(true)}>
          Propose this run for publication
        </button>
      ) : (
        <>
          <div className="banner warn" style={{ marginBottom: 10 }}>
            This does not publish anything. It puts the screening in a
            <b> reviewer's</b> queue. Write for someone who has never heard the word
            “conformal” — no P10/P90, no species codes, no model jargon.
          </div>

          <Field label="Headline" htmlFor="adv-head"
                 hint="What has been assessed, and where. Not what has happened.">
            <input id="adv-head" value={headline} maxLength={200}
                   onChange={(e) => setHeadline(e.target.value)}
                   placeholder="Groundwater screening published for Bagjata area" />
          </Field>

          <Field label="What it means" htmlFor="adv-mean"
                 hint="The hypothetical premise is added automatically and cannot be
                       removed — you do not need to write it yourself.">
            <textarea id="adv-mean" rows={5} value={meaning}
                      onChange={(e) => setMeaning(e.target.value)}
                      placeholder="A model of what would happen to groundwater if a uranium in-situ recovery operation ran at this location…" />
          </Field>

          <Field label="What to do — optional" htmlFor="adv-todo"
                 hint="Who to contact, and what a household water test costs.">
            <textarea id="adv-todo" rows={3} value={todo}
                      onChange={(e) => setTodo(e.target.value)} />
          </Field>

          <div className="row" style={{ gap: 6 }}>
            <button className="btn primary grow" disabled={!ok || propose.isPending}
                    onClick={() => propose.mutate()}>
              {/* R11: said "Send to regulator" after the role was retired in R7,
                  so it named a queue nobody could be in. An admin reviewing their
                  own proposal sees what actually happens next. */}
              {propose.isPending ? "Submitting…"
                : canAdmin(me?.role) ? "Propose for publication"
                : "Send for review"}
            </button>
            <button className="btn ghost" onClick={() => setOpen(false)}>Cancel</button>
          </div>
          {!ok && (
            <div className="muted small" style={{ marginTop: 6 }}>
              A headline of at least 8 characters and an explanation of at least 20
              are required — a one-word advisory is not one a resident can act on.
            </div>
          )}
          <ErrorNote error={propose.error} />
        </>
      )}

      <div className="muted small" style={{ marginTop: 8 }}>
        Publication is an administrator's decision. The footprint and the blocks it actually
        reaches are computed when you propose, so the reviewer decides against a real
        extent — which for a run of this kind is usually a few hectares inside one
        block, not the block itself.
      </div>
    </>
  );
}

/** Shared renderer for "what this footprint actually reaches". */
export function AffectedBlocks({ advisory }: { advisory: Advisory }) {
  const blocks = advisory.affected_blocks ?? [];
  const ha = advisory.footprint_ha;

  if (ha === null) {
    return (
      <div className="banner">
        <strong>No modelled extent.</strong> The engine produced no area above the
        screening limit for this run — outside an ore zone that is the correct
        answer, not a missing one.
      </div>
    );
  }

  return (
    <>
      <div className="readonly-val" style={{ marginBottom: 6 }}>
        <span className="muted small">Modelled footprint</span>
        <span><span className="rv-v">{fmt(ha, 2)}</span><span className="rv-u"> ha</span></span>
      </div>

      {blocks.length === 0 ? (
        <div className="banner ok">
          The modelled footprint does not reach any administrative block boundary.
        </div>
      ) : (
        <>
          <div className="table-scroll">
            <table className="grid">
              <thead>
                <tr><th>Block</th><th>District</th><th>Overlap</th></tr>
              </thead>
              <tbody>
                {blocks.map((b) => (
                  <tr key={b.id}>
                    <td>{b.name}</td>
                    <td className="muted">{b.district ?? "–"}</td>
                    <td className="mono">{fmt(b.overlap_ha, 2)} ha</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="muted small" style={{ marginTop: 6, lineHeight: "var(--lh-base)" }}>
            {blocks.length === 1
              ? <>The footprint lies within <b>one block</b>, covering{" "}
                  {fmt(blocks[0].overlap_ha, 2)} ha of it. A block is on the order of
                  tens of thousands of hectares, so this is a small part of it — not
                  the whole area.</>
              : <>The footprint touches <b>{blocks.length} blocks</b>, covering a few
                  hectares of each. That is the modelled extent, not the area at risk
                  across those blocks.</>}
            {" "}Block is the finest resolution available: there is no village or
            settlement layer in the source datasets.
          </div>
        </>
      )}
    </>
  );
}
