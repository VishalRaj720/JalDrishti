/**
 * Opens the 3-D site block for a run. The viewer and three.js load only when
 * someone asks for them, so the Console itself does not grow by a 3-D engine.
 */
import { lazy, Suspense, useEffect, useState } from "react";
import { Loading } from "../components/bits";
import type { SiteBlock3DProps } from "./SiteBlock3D";

const SiteBlock3D = lazy(() => import("./SiteBlock3D"));

export default function SiteBlockLauncher(
  { run, site, defaultYear }: Omit<SiteBlock3DProps, "onClose">,
) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open]);
  if (!site.location) return null;
  return (
    <>
      <button className="btn block" style={{ marginTop: 10 }} onClick={() => setOpen(true)}>
        Open the 3-D site block
      </button>
      <div className="muted small" style={{ marginTop: 4 }}>
        The ground, the aquifer layers, this run&apos;s plume on the ore horizon, the fronts
        climbing year by year, and CGWB&apos;s boreholes where any exist.
      </div>
      {open && (
        <Suspense fallback={<div className="b3-scrim"><Loading label="Loading the 3-D view…" /></div>}>
          <SiteBlock3D run={run} site={site} defaultYear={defaultYear}
                       onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </>
  );
}
