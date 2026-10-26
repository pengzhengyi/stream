/**
 * @file The views to move between: a rail, tabs, or a tab bar, as the width allows.
 */

import {
  DownloadSimpleIcon,
  type Icon,
  MicrophoneStageIcon,
  MusicNotesSimpleIcon,
  PlaylistIcon,
  VinylRecordIcon,
} from "@phosphor-icons/react";

import { type Route, hrefOf } from "../routes";

type Top = "songs" | "artists" | "albums" | "downloaded" | "playlists";

const TOPS: readonly { readonly view: Top; readonly label: string; readonly icon: Icon }[] = [
  { view: "songs", label: "Songs", icon: MusicNotesSimpleIcon },
  { view: "artists", label: "Artists", icon: MicrophoneStageIcon },
  { view: "albums", label: "Albums", icon: VinylRecordIcon },
  { view: "downloaded", label: "Downloaded", icon: DownloadSimpleIcon },
  { view: "playlists", label: "Playlists", icon: PlaylistIcon },
];

/** The top view a route belongs to: an artist's Tracks belong to Artists, and so on. */
function topOf(route: Route): Top | undefined {
  switch (route.view) {
    case "artist":
      return "artists";
    case "album":
      return "albums";
    case "playlist":
      return "playlists";
    case "search":
      return undefined;
    default:
      return route.view;
  }
}

/** Links to each view, the current one marked. */
export function Nav({ route }: { readonly route: Route }) {
  const top = topOf(route);
  return (
    <nav className="views" aria-label="Views">
      <ul>
        {TOPS.map(({ view, label, icon: ViewIcon }) => {
          const current = view === top;
          return (
            <li key={view}>
              <a
                className="view-link"
                href={hrefOf({ view })}
                aria-current={current ? "page" : undefined}
              >
                <ViewIcon weight={current ? "fill" : "regular"} aria-hidden />
                <span>{label}</span>
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
