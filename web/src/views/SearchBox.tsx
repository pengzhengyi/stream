/**
 * @file The search box: what to look for, and where, the Library or a music site.
 *
 * Only the Library can be searched yet; a site a plugin provides shows as a
 * choice that says so, until searching it exists.
 */

import { MagnifyingGlassIcon } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

import { type Route, navigate } from "../routes";

/** How long after typing stops the search runs. */
const SETTLE_MS = 150;

const SITE_NAMES: Record<string, string> = { bilibili: "Bilibili" };

/** Search the Library as you type, showing what it found. */
export function SearchBox({
  route,
  providers,
}: {
  readonly route: Route;
  readonly providers: readonly string[];
}) {
  const shown = route.view === "search" ? route.query : "";
  const [query, setQuery] = useState(shown);
  const [seen, setSeen] = useState(shown);
  const settling = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Back, Forward, or a link changes the search shown; the box follows.
  if (shown !== seen) {
    setSeen(shown);
    setQuery(shown);
  }
  useEffect(
    () => () => {
      clearTimeout(settling.current);
    },
    [],
  );

  const searchFor = (text: string) => {
    clearTimeout(settling.current);
    settling.current = setTimeout(() => {
      // The first letter opens the results; the rest change them in place.
      navigate({ view: "search", query: text }, { replace: route.view === "search" });
    }, SETTLE_MS);
  };

  return (
    <search className="search">
      <label className="search-field">
        <MagnifyingGlassIcon className="search-glass" weight="regular" aria-hidden />
        <span className="visually-hidden">Search</span>
        <input
          type="search"
          value={query}
          placeholder="Search songs, artists, albums"
          onChange={(event) => {
            setQuery(event.currentTarget.value);
            searchFor(event.currentTarget.value);
          }}
        />
      </label>
      {providers.length > 0 && (
        <div className="scope" role="radiogroup" aria-label="Search in">
          <label>
            <input type="radio" name="scope" checked readOnly />
            Library
          </label>
          {providers.map((provider) => {
            const name = SITE_NAMES[provider] ?? provider;
            return (
              <label key={provider} title={`Searching ${name} isn't available yet`}>
                <input type="radio" name="scope" disabled />
                {name}
              </label>
            );
          })}
        </div>
      )}
    </search>
  );
}
