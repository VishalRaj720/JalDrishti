/**
 * Bulk ingest — the five admin upload endpoints, given the UI they never had.
 *
 * WHY THIS EXISTS. `POST /ingest/{districts,subdistricts,aquifers}/geojson`,
 * `/groundwater-levels/json` and `/water-quality/csv` have been implemented,
 * guarded and tested since early in the project. Nothing in the portal called
 * any of them; `Administration.tsx` carried a `Planned` placeholder admitting
 * so. The proposal's third deliverable is a tool "for stakeholders to input
 * data", and until now the only way in was curl.
 *
 * WHY IT IS DELIBERATELY BLUNT. These are upserts against reference geography
 * and the measured record — the inputs every downstream number rests on. So the
 * screen does three things rather than looking clever: it says exactly what each
 * endpoint will do before you pick a file, it refuses obviously wrong file types
 * client-side, and it renders the server's whole response rather than a
 * green tick. An ingest that reports "412 rows" when you expected 397 is the
 * signal you came for.
 *
 * These write to the DATABASE. `Datasets/` — what the physics engine reads — is
 * a separate store reached through `/dataset-sync/*`, and the header on this
 * page says so, because an admin who uploads here and expects the model to
 * change would otherwise be quietly wrong.
 */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { upload } from "../api/client";
import { ErrorNote } from "../components/bits";

type Target = {
  key: string;
  path: string;
  label: string;
  accept: string;
  what: string;
  caution?: string;
};

const TARGETS: Target[] = [
  {
    key: "districts", path: "/ingest/districts/geojson",
    label: "District boundaries", accept: ".geojson,.json",
    what: "Upserts district polygons from a GeoJSON FeatureCollection, matched "
        + "by name.",
    caution: "Districts are the parent of every block, well and sample. "
           + "Replacing a boundary re-homes everything inside it.",
  },
  {
    key: "subdistricts", path: "/ingest/subdistricts/geojson",
    label: "Block (sub-district) boundaries", accept: ".geojson,.json",
    what: "Upserts block polygons and links each to its district.",
    caution: "Blocks are the unit every citizen alert and advisory is scoped "
           + "to. A changed boundary changes who gets told.",
  },
  {
    key: "aquifers", path: "/ingest/aquifers/geojson",
    label: "Aquifer polygons", accept: ".geojson,.json",
    what: "Upserts aquifer extents and their hydrogeological attributes.",
  },
  {
    key: "levels", path: "/ingest/groundwater-levels/json",
    label: "Groundwater level readings", accept: ".json",
    what: "Appends station water-level readings. Feeds the level-trend "
        + "analysis and, after a rebuild, the flow field.",
  },
  {
    key: "quality", path: "/ingest/water-quality/csv",
    label: "Water-quality samples", accept: ".csv",
    what: "Creates monitoring wells deduped by (lat, lon) and appends samples. "
        + "Derives TDS = 0.65 x EC with tds_derived=true where EC is present "
        + "and TDS is not.",
    caution: "This is the record the IS 10500 assessment reads. A bad row "
           + "becomes a banded result on the public map.",
  },
];

function One({ t }: { t: Target }) {
  const [file, setFile] = useState<File | null>(null);

  const run = useMutation({
    mutationFn: () => upload<Record<string, unknown>>(t.path, file!),
  });

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="row wrap" style={{ alignItems: "baseline" }}>
        <strong>{t.label}</strong>
        <span className="spacer grow" />
        <code className="muted small">POST {t.path}</code>
      </div>

      <p className="muted small" style={{ marginTop: 6 }}>{t.what}</p>
      {t.caution && (
        <div className="banner warn" style={{ margin: "6px 0" }}>{t.caution}</div>
      )}

      <div className="row wrap" style={{ marginTop: 6 }}>
        <input
          type="file"
          accept={t.accept}
          onChange={(e) => { run.reset(); setFile(e.target.files?.[0] ?? null); }}
        />
        <button className="btn" disabled={!file || run.isPending}
                onClick={() => run.mutate()}>
          {run.isPending ? "Uploading…" : "Upload"}
        </button>
        {file && (
          <span className="muted small">
            {file.name} · {(file.size / 1024).toFixed(0)} KB
          </span>
        )}
      </div>

      <ErrorNote error={run.error} />

      {run.data && (
        <>
          <div className="banner" style={{ marginTop: 8 }}>
            Upload accepted. The server's full response is below — read the counts
            rather than the absence of an error.
          </div>
          <pre className="mono small"
               style={{ maxHeight: 220, overflow: "auto", marginTop: 6 }}>
            {JSON.stringify(run.data, null, 2)}
          </pre>
        </>
      )}
    </div>
  );
}

export default function Ingest() {
  return (
    <div className="page">
      <div className="page-head">
        <h1>Bulk ingest</h1>
        <p>
          Upload reference geography and measured records. Admin only, and every
          upload is written to the audit trail with the file's checksum.
        </p>
      </div>

      <div className="banner warn" style={{ marginBottom: 14 }}>
        <strong>These write to the database, not to the model's inputs.</strong>{" "}
        The physics engine reads files under <code>Datasets/</code>, which are
        changed through the Dataset manager and the sync on Data&nbsp;&amp;&nbsp;gaps.
        Uploading here changes what the portal reports; it does not change what a
        simulation computes until those datasets are synced and, where the
        baked artefacts are affected, rebuilt.
      </div>

      {TARGETS.map((t) => <One key={t.key} t={t} />)}

      <div className="muted small">
        All five endpoints upsert rather than replace, and record a
        <code> dataset_versions</code> row keyed on the file's checksum — so
        re-uploading an identical file is detectable and is not a silent
        duplicate.
      </div>
    </div>
  );
}
