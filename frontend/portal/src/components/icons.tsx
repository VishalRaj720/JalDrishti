/**
 * The portal's icons: a small inline-SVG set, no dependency.
 *
 * R16. The header used 💧 🔔 ☰ 🟢 as its icons. Emoji render as whatever the
 * viewer's platform ships — a blue teardrop on one machine, a cartoon on
 * another, a tofu box on a locked-down government desktop — and they cannot
 * take the theme's colour, which is why the "model in sync" dot could not
 * follow the palette. Every glyph below is a 24-unit stroke path that inherits
 * `currentColor`, so it reads the same on every platform and in both themes.
 *
 * Kept deliberately small. An icon library would bring a thousand glyphs for
 * the fourteen this product uses, and would make it easy to decorate with
 * icons where a word does the job.
 */
import type { SVGProps } from "react";

const PATHS = {
  // Brand: a drop with a groundwater line through it.
  drop: "M12 2.7c-3.6 4.4-6.5 8-6.5 11.3a6.5 6.5 0 0 0 13 0c0-3.3-2.9-6.9-6.5-11.3Z M7 15.5c1.6 1 3.4 1 5 0s3.4-1 5 0",
  bell: "M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9 M10.3 21a1.9 1.9 0 0 0 3.4 0",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  close: "M18 6 6 18 M6 6l12 12",
  pin: "M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z M12 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  locate: "M12 2v3 M12 19v3 M2 12h3 M19 12h3 M12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12Z M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z M12 1v2 M12 21v2 M4.2 4.2l1.4 1.4 M18.4 18.4l1.4 1.4 M1 12h2 M21 12h2 M4.2 19.8l1.4-1.4 M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z",
  check: "M20 6 9 17l-5-5",
  alert: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z M12 9v4 M12 17h.01",
  mail: "M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z M22 6l-10 7L2 6",
  chevron: "m6 9 6 6 6-6",
  external: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6 M15 3h6v6 M10 14 21 3",
  map: "M1 6v16l7-4 8 4 7-4V2l-7 4-8-4-7 4Z M8 2v16 M16 6v16",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z",
  activity: "M22 12h-4l-3 9L9 3l-3 9H2",
  users: "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M23 21v-2a4 4 0 0 0-3-3.9 M16 3.1a4 4 0 0 1 0 7.8",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z M21 21l-4.3-4.3",
  arrow: "M5 12h14 M12 5l7 7-7 7",
  layers: "m12 2 10 5-10 5L2 7l10-5Z M2 17l10 5 10-5 M2 12l10 5 10-5",
  flask: "M9 3h6 M10 3v6.3L4.5 19a1.5 1.5 0 0 0 1.3 2.2h12.4a1.5 1.5 0 0 0 1.3-2.2L14 9.3V3",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M12 6v6l4 2",
  send: "m22 2-7 20-4-9-9-4Z M22 2 11 13",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M12 16v-4 M12 8h.01",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18, strokeWidth = 1.9, ...rest }:
  { name: IconName; size?: number; strokeWidth?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round"
         strokeLinejoin="round" aria-hidden focusable="false" className="ico" {...rest}>
      <path d={PATHS[name]} />
    </svg>
  );
}

/** The brand mark: the drop on its accent tile. */
export function Mark({ size = 32 }: { size?: number }) {
  return (
    <span className="hdr-mark" style={{ width: size, height: size }} aria-hidden>
      <Icon name="drop" size={Math.round(size * 0.62)} strokeWidth={2.2} />
    </span>
  );
}
