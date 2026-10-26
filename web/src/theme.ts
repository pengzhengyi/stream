/**
 * @file The color theme: the system's, or light or dark whatever the system says.
 *
 * The choice is kept per browser. Pico reads `data-theme` on the root element;
 * without it, the page follows the system.
 */

import { useSyncExternalStore } from "react";

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

let shown: Theme | undefined;
const listeners = new Set<() => void>();

/** Show the page in `theme`, and remember it for this browser. */
export function applyTheme(theme: Theme): void {
  shown = theme;
  for (const listener of listeners) {
    listener();
  }
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

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const current = () => shown ?? savedTheme();

/** The theme chosen, and a way to choose another; every switch on the page agrees. */
export function useTheme(): [Theme, (theme: Theme) => void] {
  return [useSyncExternalStore(subscribe, current), applyTheme];
}
