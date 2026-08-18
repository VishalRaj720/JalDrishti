/**
 * Panel chrome shared by both map screens: a draggable floating overlay and a
 * drag-to-resize edge for the rail and the drawer.
 *
 * THREE THINGS ARE DELIBERATE HERE.
 *
 * 1. **Pointer events, not mouse events.** The portal is used on tablets, and
 *    `onMouseDown`/`onMouseMove` never fire for touch. `setPointerCapture` also
 *    means a fast drag that leaves the element keeps tracking, which a
 *    mousemove-on-window listener only approximates.
 *
 * 2. **`sessionStorage`, not `localStorage`.** Same reasoning `useRail` gives:
 *    a layout preference that survives a sign-out on a shared machine is a
 *    preference nobody set.
 *
 * 3. **Resizing is suppressed below 1024px.** Below that breakpoint the drawer
 *    is absolutely positioned and below 768px it is a bottom sheet, so an
 *    inline pixel width would fight the responsive contract in `layout.css`
 *    rather than extend it. The stored width is kept — it simply is not applied
 *    until the viewport is wide enough for a real column again.
 */
import {
  useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode,
} from "react";

/** Width below which panels stop being in-flow columns (layout.css §RESPONSIVE). */
const RESIZE_MIN_VIEWPORT = 1024;

function readNum(key: string, fallback: number): number {
  const raw = sessionStorage.getItem(key);
  const n = raw === null ? NaN : Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

/**
 * A panel width the user can drag, persisted for the session.
 *
 * Returns the style to spread onto the panel — `flex` is set alongside `width`
 * because the panel is a flex item and `flex: 0 0 var(--rail-w)` from the
 * stylesheet would otherwise win.
 */
export function useResizableWidth(
  key: string,
  { min, max, initial, edge }: { min: number; max: number; initial: number; edge: "left" | "right" },
) {
  const storageKey = `jaldrishti.width.${key}`;
  const [width, setWidth] = useState(() =>
    Math.min(max, Math.max(min, readNum(storageKey, initial))));
  const [wide, setWide] = useState(
    () => typeof window === "undefined"
      || window.matchMedia(`(min-width: ${RESIZE_MIN_VIEWPORT}px)`).matches);
  const [dragging, setDragging] = useState(false);

  // The inline width must drop away the moment the panel stops being a column,
  // so the media query is watched rather than read once.
  useEffect(() => {
    const mq = window.matchMedia(`(min-width: ${RESIZE_MIN_VIEWPORT}px)`);
    const sync = () => setWide(mq.matches);
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = width;
    const el = e.currentTarget;
    // `setPointerCapture` THROWS if the pointer is no longer active — a real
    // case when a drag begins on a pointer the browser has already released.
    // It used to run before the listeners were attached, so the throw left the
    // handle in its dragging state with nothing listening: the panel simply
    // never resized and nothing said why. Capture is an optimisation here;
    // losing it degrades a fast drag, it does not break one.
    try { el.setPointerCapture(e.pointerId); } catch { /* not capturable */ }
    setDragging(true);

    const move = (ev: PointerEvent) => {
      // A left-edge handle (the drawer) grows the panel as the pointer moves
      // LEFT, so the delta is inverted against a right-edge handle (the rail).
      const delta = edge === "left" ? startX - ev.clientX : ev.clientX - startX;
      setWidth(Math.min(max, Math.max(min, startW + delta)));
    };
    const up = () => {
      setDragging(false);
      try { el.releasePointerCapture?.(e.pointerId); } catch { /* already gone */ }
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  }, [width, min, max, edge]);

  useEffect(() => {
    sessionStorage.setItem(storageKey, String(width));
  }, [width, storageKey]);

  const reset = useCallback(() => setWidth(initial), [initial]);

  const style = wide ? { width, flex: `0 0 ${width}px` } : undefined;

  const handle = (
    <div
      className={`resize-handle ${edge} ${dragging ? "on" : ""}`}
      onPointerDown={onPointerDown}
      onDoubleClick={reset}
      role="separator"
      aria-orientation="vertical"
      aria-label="Drag to resize this panel, double-click to reset"
      title="Drag to resize · double-click to reset"
    />
  );

  return { width, style, handle, dragging, reset };
}

/**
 * A floating overlay the user can drag anywhere within its container.
 *
 * Position is stored as a fraction of the container, not as pixels: the map
 * area changes width whenever the rail or the drawer opens, and a panel pinned
 * at `left: 900px` would end up off-screen when the window narrows. Fractions
 * survive that, and the result is clamped on every layout pass anyway.
 */
export function FloatingPanel({
  storageKey, title, children, defaultCorner = "bottom-left", className = "",
}: {
  storageKey: string;
  title: ReactNode;
  children: ReactNode;
  defaultCorner?: "bottom-left" | "bottom-right" | "top-left";
  className?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const posKey = `jaldrishti.panel.${storageKey}.pos`;
  const openKey = `jaldrishti.panel.${storageKey}.open`;

  const [open, setOpen] = useState(() => sessionStorage.getItem(openKey) !== "0");
  const [pos, setPos] = useState<{ fx: number; fy: number } | null>(() => {
    try {
      const raw = sessionStorage.getItem(posKey);
      if (!raw) return null;
      const p = JSON.parse(raw);
      return typeof p?.fx === "number" && typeof p?.fy === "number" ? p : null;
    } catch { return null; }
  });
  const [dragging, setDragging] = useState(false);
  const [px, setPx] = useState<{ left: number; top: number } | null>(null);

  useEffect(() => { sessionStorage.setItem(openKey, open ? "1" : "0"); }, [open, openKey]);

  /** Fractions → pixels, clamped so the panel can never leave its container. */
  const place = useCallback(() => {
    const el = ref.current;
    const parent = el?.offsetParent as HTMLElement | null;
    if (!el || !parent || !pos) { setPx(null); return; }
    const pw = parent.clientWidth, ph = parent.clientHeight;
    const w = el.offsetWidth, h = el.offsetHeight;
    setPx({
      left: Math.min(Math.max(pos.fx * pw, 0), Math.max(pw - w, 0)),
      top: Math.min(Math.max(pos.fy * ph, 0), Math.max(ph - h, 0)),
    });
  }, [pos]);

  useLayoutEffect(place, [place, open]);

  useEffect(() => {
    if (!pos) return;
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [pos, place]);

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    // Let the collapse button be a button.
    if ((e.target as HTMLElement).closest("button")) return;
    const el = ref.current;
    const parent = el?.offsetParent as HTMLElement | null;
    if (!el || !parent) return;
    e.preventDefault();

    const box = el.getBoundingClientRect();
    const pbox = parent.getBoundingClientRect();
    const grabX = e.clientX - box.left;
    const grabY = e.clientY - box.top;
    const handle = e.currentTarget;
    try { handle.setPointerCapture(e.pointerId); } catch { /* not capturable */ }
    setDragging(true);

    const move = (ev: PointerEvent) => {
      const pw = parent.clientWidth, ph = parent.clientHeight;
      const left = Math.min(Math.max(ev.clientX - pbox.left - grabX, 0),
                            Math.max(pw - el.offsetWidth, 0));
      const top = Math.min(Math.max(ev.clientY - pbox.top - grabY, 0),
                           Math.max(ph - el.offsetHeight, 0));
      setPx({ left, top });
      setPos({ fx: pw ? left / pw : 0, fy: ph ? top / ph : 0 });
    };
    const up = () => {
      setDragging(false);
      try { handle.releasePointerCapture?.(e.pointerId); } catch { /* already gone */ }
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  };

  useEffect(() => {
    if (pos) sessionStorage.setItem(posKey, JSON.stringify(pos));
  }, [pos, posKey]);

  return (
    <div
      ref={ref}
      className={`map-ov floater ${className} ${pos ? "placed" : defaultCorner} ${dragging ? "dragging" : ""}`}
      style={px ? { left: px.left, top: px.top, right: "auto", bottom: "auto" } : undefined}
    >
      <div className="floater-bar" onPointerDown={onPointerDown}>
        <span className="floater-grip" aria-hidden="true" />
        <span className="ov-title" style={{ margin: 0 }}>{title}</span>
        <button
          className="floater-btn"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          title={open ? "Collapse" : "Expand"}
          aria-label={open ? "Collapse this panel" : "Expand this panel"}
        >{open ? "−" : "+"}</button>
      </div>
      {open && <div className="floater-body">{children}</div>}
    </div>
  );
}
