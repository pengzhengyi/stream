/**
 * @file The color theme: the system's, or light or dark whatever the system says.
 *
 * The choice is kept per browser. Pico reads `data-theme` on the root element;
 * without it, the page follows the system.
 */

import { useState } from "react";

/** Which colors the page uses. */
export type Theme = "system" | "light" | "dark";

export const THEMES: readonly Theme[] = ["system", "light", "dark"];
const KEY = "medleyplay.theme";

/** Return the theme this browser chose, or the system's. */
export function savedTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    return THEMES.find((theme) => theme === saved) ?? "system";
  } catch {
    return "system";
  }
}

/** Show the page in `theme`, and remember it for this browser. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = theme;
  }
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // A browser that keeps nothing still shows the theme until the page closes.
  }
}

/** The theme chosen, and a way to choose another. */
export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setTheme] = useState(savedTheme);
  return [
    theme,
    (chosen) => {
      applyTheme(chosen);
      setTheme(chosen);
    },
  ];
}
