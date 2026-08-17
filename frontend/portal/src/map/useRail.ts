/**
 * Rail collapse state, shared by every screen that has a rail.
 *
 * Three rules, all deliberate:
 *
 * 1. **Manual only.** Nothing collapses the rail on the user's behalf — not
 *    pressing play on the timelapse, not opening the registration drawer, not
 *    a narrow viewport. Chrome that moves on its own is chrome the user has to
 *    re-check every time they look away.
 * 2. **Independent of the drawer.** The motivating case is registering a site:
 *    a dozen parameters in the right-hand drawer, and the user wants the left
 *    rail out of the way at that moment. Neither panel drives the other.
 * 3. **Sticky within the session.** Collapsing it on the Map Console and then
 *    visiting the Studio should not put it back. `sessionStorage`, not
 *    `localStorage` — a preference that survives a sign-out on a shared
 *    machine is a preference nobody set.
 */
import { useCallback, useEffect, useState } from "react";
import type L from "leaflet";

const KEY = "jaldrishti.rail.collapsed";

export function useRail(map?: React.MutableRefObject<L.Map | null>) {
  const [collapsed, setCollapsed] = useState<boolean>(
    () => sessionStorage.getItem(KEY) === "1");

  const toggle = useCallback(() => {
    setCollapsed((c) => {
      sessionStorage.setItem(KEY, c ? "0" : "1");
      return !c;
    });
  }, []);

  // Leaflet caches the container size and will keep serving tiles for the old
  // width until told otherwise, so the map stays letterboxed after the rail
  // slides away. The delay clears the CSS transition; `animate: false` stops
  // the recentre from being a second, competing animation.
  useEffect(() => {
    if (!map?.current) return;
    const t = setTimeout(() => map.current?.invalidateSize({ animate: false }), 230);
    return () => clearTimeout(t);
  }, [collapsed, map]);

  return { collapsed, toggle };
}
