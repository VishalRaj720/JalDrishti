/**
 * Publishing straight from a preview run.
 *
 * THE STEP THAT WAS REMOVED. Publishing used to require the author to press
 * *Save this run* first, and only then did anything about publication appear.
 * Two presses, in a fixed order, where the first one carried no decision — by
 * the time somebody is writing a headline they have already decided to keep the
 * run. Forgetting the save did not protect anything; it just hid the next
 * button and read as "publishing is broken".
 *
 * WHAT DID NOT CHANGE. The run is still stored before the advisory exists. It
 * is stored *by* the publish call (`POST /advisories/publish-run`) instead of by
 * the user, so a published statement still cites a durable, re-derivable result
 * — the guarantee that made saving a precondition in the first place. Saving
 * separately still works and is still the right move when you want to keep a
 * run you are not publishing.
 *
 * WHAT IS DELIBERATELY STILL TWO THINGS. Proposing and deciding. An analyst
 * pressing this gets a proposal in the review queue; only an admin's press
 * reaches residents, and the button says which one is about to happen. A
 * screening tool where the person who ran the model is also the person who
 * announces it has no review step at all.
 */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Advisory } from "../api/client";
import { canAdmin, useAuth } from "../auth";
import { ErrorNote, Field } from "../components/bits";

type PublishResult = {
  advisory: Advisory;
  run_id: string;
  run_was_saved: boolean;
  published: boolean;
  note: string;
};

export default function PublishFromPreview({
  siteId, species, timeYears, restorationYears, onSaved,
}: {
  siteId: string;
  species: string;
  timeYears: number;
  restorationYears: number;
  /** Lets the Console show the stored run this call created. */
  onSaved: (runId: string) => void;
}) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [headline, setHeadline] = useState("");
  const [meaning, setMeaning] = useState("");
  const [todo, setTodo] = useState("");
  const [done, setDone] = useState<PublishResult | null>(null);

  const admin = canAdmin(me?.role);

  const publish = useMutation({
    mutationFn: () => api.post<PublishResult>("/advisories/publish-run", {
      isr_point_id: siteId,
      species, time_years: timeYears, restoration_years: restorationYears,
      headline: headline.trim(),
      what_it_means: meaning.trim(),
      what_to_do: todo.trim() || null,
    }),
    onSuccess: (r) => {
      setDone(r);
      setOpen(false); setHeadline(""); setMeaning(""); setTodo("");
      onSaved(r.run_id);
      qc.invalidateQueries({ queryKey: ["advisories"] });
      qc.invalidateQueries({ queryKey: ["runs", siteId] });
    },
  });

  const ok = headline.trim().length >= 8 && meaning.trim().length >= 20;

  if (done) {
    return (
      <div className={`banner ${done.published ? "ok" : ""}`} style={{ marginTop: 10 }}>
        <strong>{done.published ? "Published." : "Sent for review."}</strong>{" "}
        {done.note}
        <div className="muted small" style={{ marginTop: 5 }}>
          Run <span className="mono">{done.run_id.slice(0, 8)}</span> was saved
          automatically and is what the advisory cites.
        </div>
        <button className="btn ghost block" style={{ marginTop: 8 }}
                onClick={() => setDone(null)}>
          Publish another
        </button>
      </div>
    );
  }

  if (!open) {
    return (
      <>
        <button className="btn block" style={{ marginTop: 8 }}
                onClick={() => setOpen(true)}>
          {admin ? "Publish this screening" : "Send this screening for review"}
        </button>
        <div className="muted small" style={{ marginTop: 6 }}>
          {admin
            ? <>Saves this run and publishes it in one step — no separate save
                needed. The saved run is what residents' advisory cites.</>
            : <>Saves this run and puts it in the administrator's review queue.
                Nothing becomes public until they decide.</>}
        </div>
      </>
    );
  }

  return (
    <div style={{ marginTop: 10 }}>
      <div className={`banner ${admin ? "warn" : ""}`} style={{ marginBottom: 10 }}>
        {admin
          ? <><b>This reaches residents.</b> Publishing raises an alert in every block
              the modelled footprint intersects. The run is saved first, automatically,
              so the statement cites a stored result.</>
          : <>This does not publish anything. It saves the run and puts the screening
              in an <b>administrator's</b> queue.</>}
        {" "}Write for someone who has never heard the word “conformal” — no
        P10/P90, no species codes, no model jargon.
      </div>

      <Field label="Headline" htmlFor="pub-head"
             hint="What has been assessed, and where. Not what has happened.">
        <input id="pub-head" value={headline} maxLength={200}
               onChange={(e) => setHeadline(e.target.value)}
               placeholder="Groundwater screening published for Bagjata area" />
      </Field>

      <Field label="What it means" htmlFor="pub-mean"
             hint="The hypothetical premise is added automatically and cannot be
                   removed — you do not need to write it yourself.">
        <textarea id="pub-mean" rows={5} value={meaning}
                  onChange={(e) => setMeaning(e.target.value)}
                  placeholder="A model of what would happen to groundwater if a uranium in-situ recovery operation ran at this location…" />
      </Field>

      <Field label="What to do — optional" htmlFor="pub-todo"
             hint="Who to contact, and what a household water test costs.">
        <textarea id="pub-todo" rows={3} value={todo}
                  onChange={(e) => setTodo(e.target.value)} />
      </Field>

      <div className="row" style={{ gap: 6 }}>
        <button className="btn primary grow" disabled={!ok || publish.isPending}
                onClick={() => publish.mutate()}>
          {publish.isPending
            ? "Saving the run and publishing…"
            : admin ? "Save run and publish" : "Save run and send for review"}
        </button>
        <button className="btn ghost" onClick={() => setOpen(false)}>Cancel</button>
      </div>

      {!ok && (
        <div className="muted small" style={{ marginTop: 6 }}>
          A headline of at least 8 characters and an explanation of at least 20 are
          required — a one-word advisory is not one a resident can act on.
        </div>
      )}
      <ErrorNote error={publish.error} />
    </div>
  );
}
