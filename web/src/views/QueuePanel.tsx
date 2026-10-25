/**
 * @file The queue: what plays next, in order, to reorder or remove.
 */

import type { Track } from "../api";
import { upNext } from "../player/queue";
import type { Player } from "../player/usePlayer";

/** What plays after the current Track. */
export function QueuePanel({
  player,
  tracks,
}: {
  readonly player: Player;
  readonly tracks: ReadonlyMap<number, Track>;
}) {
  const entries = upNext(player.queue);
  return (
    <section className="queue" aria-label="Up next">
      <header>
        <h2>Up next</h2>
        <button type="button" onClick={player.clear} disabled={entries.length === 0}>
          Clear
        </button>
      </header>
      {entries.length === 0 ? (
        <p className="empty">Nothing queued.</p>
      ) : (
        <ol>
          {entries.map((entry, index) => {
            const title = tracks.get(entry.trackId)?.title ?? "A Track no longer here";
            return (
              <li key={entry.key}>
                <span>{title}</span>
                <button
                  type="button"
                  aria-label={`Move ${title} up`}
                  disabled={index === 0}
                  onClick={() => {
                    player.move(entry.key, -1);
                  }}
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={`Move ${title} down`}
                  disabled={index === entries.length - 1}
                  onClick={() => {
                    player.move(entry.key, 1);
                  }}
                >
                  ↓
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${title}`}
                  onClick={() => {
                    player.remove(entry.key);
                  }}
                >
                  ✕
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
