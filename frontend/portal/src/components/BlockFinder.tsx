/**
 * "Where do you live?" — one control, used before AND after sign-in.
 *
 * R16. The alert system can only tell a person about their own water if it
 * knows where that is, and until now the only way it learned was a resident
 * finding the Alerts screen, then My Area, then a search box, then pressing
 * Follow. Registration now asks up front, and this is the control it asks
 * with. It talks only to the unauthenticated `/public/risk/blocks/*` routes,
 * so the same component serves the registration form (no token yet) and the
 * My Area picker (token present, irrelevant here).
 *
 * Two ways in, because they fail differently:
 *
 *   TYPE A NAME   works everywhere, needs the person to know their block.
 *   USE LOCATION  needs the browser's permission and a device that has a fix;
 *                 on a laptop in an office it often resolves to the wrong
 *                 city, and the result is shown as a name to confirm rather
 *                 than silently accepted. A point outside every Jharkhand
 *                 block is reported as exactly that.
 *
 * Block, not village: `Datasets/` has no settlement layer, and offering a
 * village search that silently resolves to a block would imply a precision
 * the data does not have.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { pub, type BlockRef } from "../api/client";
import { Icon } from "./icons";

export default function BlockFinder({
  value, onChange, autoFocus = false, compact = false,
}: {
  value: BlockRef | null;
  onChange: (b: BlockRef | null) => void;
  autoFocus?: boolean;
  compact?: boolean;
}) {
  const [q, setQ] = useState("");
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);

  // Debounce keystrokes a little: the search is cheap but the list flickers
  // if every character re-renders it.
  const [term, setTerm] = useState("");
  useEffect(() => {
    const t = window.setTimeout(() => setTerm(q.trim()), 180);
    return () => window.clearTimeout(t);
  }, [q]);

  const results = useQuery({
    queryKey: ["public-blocks", term],
    queryFn: () => pub.blocksSearch(term, 30),
    enabled: !value && term.length >= 2,
  });

  function locate() {
    setLocError(null);
    if (!("geolocation" in navigator)) {
      setLocError("This browser cannot share a location. Type your block name instead.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const b = await pub.blockAt(pos.coords.latitude, pos.coords.longitude);
          onChange(b);
        } catch (err) {
          setLocError(err instanceof Error
            ? err.message
            : "Could not match that location to a block.");
        } finally {
          setLocating(false);
        }
      },
      (err) => {
        setLocating(false);
        setLocError(err.code === err.PERMISSION_DENIED
          ? "Location permission was refused. Type your block name instead."
          : "Could not get a location from this device. Type your block name instead.");
      },
      { enableHighAccuracy: false, timeout: 12_000, maximumAge: 300_000 },
    );
  }

  if (value) {
    return (
      <div className="block-chosen">
        <Icon name="pin" />
        <div className="grow">
          <div className="nm">{value.name}</div>
          <div className="mt">{value.district ?? "Jharkhand"}</div>
        </div>
        <button type="button" className="btn ghost" onClick={() => { onChange(null); setQ(""); }}>
          Change
        </button>
      </div>
    );
  }

  return (
    <div className="block-finder">
      <div className="row">
        <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus={autoFocus}
               placeholder="Type your block or district…" aria-label="Search for your block"
               autoComplete="off" />
        <button type="button" className="btn" onClick={locate} disabled={locating}
                title="Use this device's location">
          {locating ? <span className="spinner" /> : <Icon name="locate" />}
          {!compact && <span>Use my location</span>}
        </button>
      </div>
      {locError && <div className="hint danger">{locError}</div>}
      {results.isLoading && <div className="hint">Searching…</div>}
      {term.length >= 2 && results.data?.length === 0 && (
        <div className="hint">No block matches “{term}”.</div>
      )}
      {!!results.data?.length && (
        <div className="block-results" role="listbox">
          {results.data.map((b) => (
            <button key={b.id} type="button" className="list-item" role="option"
                    onClick={() => onChange(b)}>
              <div>
                <div className="nm">{b.name}</div>
                <div className="mt">{b.district ?? ""}</div>
              </div>
              <span className="chip info">Choose</span>
            </button>
          ))}
        </div>
      )}
      {!compact && term.length < 2 && !locError && (
        <div className="hint">
          Blocks are the smallest areas the groundwater record covers.
        </div>
      )}
    </div>
  );
}
