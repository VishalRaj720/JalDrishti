/**
 * The citizen surface — the only screen written for someone who has never heard
 * the word "conformal".
 *
 * No site points, no coordinates, no simulation output, no uncertainty bands.
 * District and block aggregates of MEASURED groundwater quality, in plain
 * language, because design §2 forbids non-staff a precise coordinate for a
 * hypothetical mine and §4.4 forbids model jargon here.
 *
 * Staff can open it too, so an official can see exactly what the public sees.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type PublicDistrictRisk } from "../api/client";
import { isStaff, useAuth } from "../auth";
import { Loading, Planned } from "../components/bits";

interface BlockRisk {
  id: string; name: string; wells: number; samples: number;
  max_uranium_ppb: number | null; band: string; what_it_means: string;
  last_sampled: string | null;
}
interface Detail {
  district: { id: string; name: string };
  blocks: BlockRisk[];
  safe_limit: number;
  what_this_is: string;
  data_gap: number;
}

const cls = (band: string) =>
  band === "High concern" ? "danger"
    : band === "Moderate concern" ? "warn"
    : band === "No data" ? "neutral" : "ok";

export default function PublicView() {
  const { me } = useAuth();
  const [id, setId] = useState<string>("");

  const list = useQuery({
    queryKey: ["public-risk"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[]; safe_limit: number; what_this_is: string }>(
      "/public/risk/districts"),
  });
  const detail = useQuery({
    queryKey: ["public-risk", id], enabled: !!id,
    queryFn: () => api.get<Detail>(`/public/risk/${id}`),
  });

  return (
    <div className="page">
      <div className="page-head">
        <h1>Groundwater near you</h1>
        <p>
          Real test results from government groundwater sampling across Jharkhand.
          Choose your district to see what was measured, and what it means.
        </p>
      </div>

      {isStaff(me?.role) && (
        <div className="banner" style={{ marginBottom: 14 }}>
          You are viewing the <strong>public surface</strong>. It deliberately shows no
          site locations, no coordinates and no simulation output.
        </div>
      )}

      <div className="banner warn" style={{ marginBottom: 16 }}>
        {list.data?.what_this_is}
      </div>

      <div className="card">
        <div className="card-title">Choose your district</div>
        {list.isLoading && <Loading />}
        <select value={id} onChange={(e) => setId(e.target.value)}>
          <option value="">— select a district —</option>
          {list.data?.districts.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </div>

      {!id && list.data && (
        <div className="card" style={{ padding: 0 }}>
          <table className="grid">
            <thead>
              <tr><th>District</th><th>Wells tested</th><th>Highest reading</th><th>Result</th></tr>
            </thead>
            <tbody>
              {list.data.districts.map((d) => (
                <tr key={d.id} style={{ cursor: "pointer" }} onClick={() => setId(d.id)}>
                  <td>{d.name}</td>
                  <td className="mono">{d.wells}</td>
                  <td className="mono">
                    {d.max_uranium_ppb ?? "–"}{" "}
                    <span className="muted">ppb</span>
                  </td>
                  <td><span className={`chip ${cls(d.band)}`}>{d.band}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="muted small" style={{ padding: "10px 12px" }}>
            The safe limit for uranium in drinking water is{" "}
            <strong>{list.data.safe_limit} ppb</strong>.
          </div>
        </div>
      )}

      {detail.isLoading && <Loading label="Loading your area…" />}

      {detail.data && (
        <>
          <div className="card">
            <div className="card-title">
              {detail.data.district.name}
              <span className="spacer grow" />
              <button className="btn ghost" onClick={() => setId("")}>All districts</button>
            </div>
            {detail.data.data_gap > 0 && (
              <div className="banner warn">
                {detail.data.data_gap} block(s) here have never been sampled. That is a
                gap in monitoring — not a clean result.
              </div>
            )}
          </div>

          {detail.data.blocks.map((b) => (
            <div className="card" key={b.id}>
              <div className="row">
                <strong>{b.name}</strong>
                <span className="spacer grow" />
                <span className={`chip ${cls(b.band)}`}>{b.band}</span>
              </div>
              <div className="muted small" style={{ marginTop: 7, lineHeight: 1.6 }}>
                {b.what_it_means}
              </div>
              <div className="muted small" style={{ marginTop: 6 }}>
                {b.wells} well(s) tested
                {b.max_uranium_ppb !== null && ` · highest reading ${b.max_uranium_ppb} ppb`}
                {b.last_sampled && ` · last sampled ${new Date(b.last_sampled).toLocaleDateString()}`}
              </div>
            </div>
          ))}

          <Planned label="Get told when the water near me changes" phase="P7"
                   why="Alert subscriptions are designed but no notification service exists yet." />
        </>
      )}
    </div>
  );
}
