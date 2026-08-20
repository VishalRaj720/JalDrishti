/**
 * Where inside a block to put the next monitoring well.
 *
 * The priority list answers *which block*; a block is 200–900 km² and nobody
 * can send a drilling rig to that. This draws the block outline, the wells that
 * already exist, and the candidate coordinates — so the recommendation becomes
 * something a person can act on rather than a row in a table.
 *
 * The criterion is geometric and stated on screen: maximum distance from any
 * existing uranium-tested well. Deliberately NOT predicted concentration —
 * siting by prediction would send crews where the model is already confident and
 * leave the blind spots blind, which is the same circularity the block ranking
 * avoids.
 */
import { useEffect, useRef } from "react";
import L from "leaflet";
import { useQuery } from "@tanstack/react-query";

import { api, type SuggestedSites } from "../api/client";
import { ErrorNote, Loading } from "../components/bits";

export default function SiteSuggestionMap({ blockId }: { blockId: string }) {
  const el = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);

  const q = useQuery({
    queryKey: ["well-sites", blockId],
    queryFn: () => api.get<SuggestedSites>(
      `/data-gaps/recommendations/${blockId}/sites?n=3`),
  });

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { zoomControl: true, scrollWheelZoom: false });
    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
      attribution: "© OpenStreetMap, © CARTO", maxZoom: 19,
    }).addTo(m);
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current, g = layer.current;
    if (!m || !g || !q.data) return;
    g.clearLayers();

    const outline = L.geoJSON(q.data.geometry as never, {
      style: { color: "#3D7EFF", weight: 2, fillOpacity: 0.06, dashArray: "5 4" },
    }).addTo(g);

    q.data.sites.forEach((s) => {
      // Numbered so a marker maps to a row in the list beneath, and hollow so it
      // reads as a proposal rather than as something that exists.
      L.marker([s.lat, s.lon], {
        icon: L.divIcon({
          className: "suggest-pin-wrap",
          html: `<div class="suggest-pin">${s.rank}</div>`,
          iconSize: [22, 22], iconAnchor: [11, 11],
        }),
      }).bindTooltip(
        `<b>Candidate ${s.rank}</b><br/>${s.lat}, ${s.lon}<br/>`
        + `${s.km_to_tested_well} km from the nearest uranium result`,
        { direction: "top" }).addTo(g);
    });

    // Fit to the block, not to the markers: the point of the picture is where
    // the candidates sit *relative to the block*, including how empty it is.
    try { m.fitBounds(outline.getBounds(), { padding: [24, 24] }); } catch { /* empty */ }
    setTimeout(() => m.invalidateSize(), 60);
  }, [q.data]);

  return (
    <div>
      {q.isLoading && <Loading label="Working out where a well would help most…" />}
      {q.error && <ErrorNote error={q.error} />}
      <div ref={el} style={{ height: 320, borderRadius: 8, overflow: "hidden" }} />

      {q.data && (
        <>
          <div className="sec">Candidate coordinates</div>
          <table className="tbl compact">
            <thead>
              <tr><th>#</th><th>Latitude</th><th>Longitude</th>
                <th>Nearest uranium result</th></tr>
            </thead>
            <tbody>
              {q.data.sites.map((s) => (
                <tr key={s.rank}>
                  <td><b>{s.rank}</b></td>
                  <td className="mono small">{s.lat}</td>
                  <td className="mono small">{s.lon}</td>
                  <td className="small">{s.km_to_tested_well} km</td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="muted small" style={{ marginTop: 8 }}>
            <b>How these were chosen.</b> {q.data.criterion}
          </p>
          <div className="banner warn">
            <b>Not a survey.</b> {q.data.caveat}
          </div>
          <p className="muted small">{q.data.determinism}</p>
        </>
      )}
    </div>
  );
}
