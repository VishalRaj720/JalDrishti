/**
 * Light and dark, chosen by the person looking.
 *
 * R16. The portal shipped dark-only. That was right when the whole product was
 * the engine dashboard on an analyst's monitor, and wrong for everything the
 * portal became: a resident reading prose on a phone in daylight, a reviewer
 * reading it projected in a bright room, a printed report. Every colour in
 * `theme.css` is a token, so the second theme is a second token set and no
 * component changes.
 *
 * LIGHT IS THE DEFAULT. The majority use is reading measured groundwater
 * results, and on a projector a dark interface turns to mud. Dark remains one
 * click away in the header for the control-room case the console was built
 * for, and the choice persists per browser.
 *
 * The attribute goes on `<html>`, not on a React root, so the login page,
 * the landing page and the app shell all read the same value and there is no
 * flash of the wrong theme before React mounts (see the inline script in
 * index.html, which applies the stored value before the bundle loads).
 */
import { useCallback, useEffect, useState } from "react";
import { Icon } from "./components/icons";

export type Theme = "light" | "dark";
const KEY = "jaldrishti.theme";

export function readTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark") return v;
  } catch { /* private mode or blocked storage */ }
  return "light";
}

export function applyTheme(t: Theme) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(KEY, t); } catch { /* ignore */ }
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(readTheme);
  useEffect(() => { applyTheme(theme); }, [theme]);
  // Keep two tabs in step.
  useEffect(() => {
    const on = (e: StorageEvent) => {
      if (e.key === KEY && (e.newValue === "light" || e.newValue === "dark")) {
        setThemeState(e.newValue);
      }
    };
    window.addEventListener("storage", on);
    return () => window.removeEventListener("storage", on);
  }, []);
  const set = useCallback((t: Theme) => setThemeState(t), []);
  return [theme, set];
}

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const [theme, setTheme] = useTheme();
  const next: Theme = theme === "light" ? "dark" : "light";
  return (
    <button type="button" className="btn ghost theme-toggle"
            onClick={() => setTheme(next)}
            aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      <Icon name={theme === "light" ? "moon" : "sun"} size={16} />
      {!compact && <span>{theme === "light" ? "Dark" : "Light"}</span>}
    </button>
  );
}
