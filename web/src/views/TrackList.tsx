/**
 * @file The Track list: every Track, to play now, next, or later.
 */

import { ListPlusIcon, QueueIcon } from "@phosphor-icons/react";

import type { Track } from "../api";
import { formatTime } from "../format";

const WHY: Record<string, string> = {
  offline: "Offline",
  unavailable: "Unavailable",
  missing: "Missing",
  cant_play: "Can't play",
};

/** Every Track; choosing one plays it and queues the Tracks after it. */
export function TrackList({
  tracks,
  playingId,
  onPlay,
  onPlayNext,
  onAdd,
}: {
  readonly tracks: readonly Track[];
  readonly playingId: number | undefined;
  readonly onPlay: (index: number) => void;
  readonly onPlayNext: (track: Track) => void;
  readonly onAdd: (track: Track) => void;
}) {
  if (tracks.length === 0) {
    return (
      <p className="empty">
        No music yet. An admin adds a Library of your own music in <a href="/docs">the API</a>, and
        its songs appear here.
      </p>
    );
  }
  return (
    <table className="tracks">
      <thead>
        <tr>
          <th scope="col" className="title-column">
            Title
          </th>
          <th scope="col" className="artist">
            Artist
          </th>
          <th scope="col" className="album">
            Album
          </th>
          <th scope="col" className="time">
            Time
          </th>
          <th scope="col" className="actions">
            <span className="visually-hidden">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {tracks.map((track, index) => {
          const playable = track.availability === "ok";
          return (
            <tr
              key={track.id}
              className={playable ? undefined : "unplayable"}
              aria-current={track.id === playingId ? "true" : undefined}
            >
              <td className="title-column">
                <div className="title-cell">
                  {track.id === playingId && <span className="bars" aria-hidden />}
                  <button
                    type="button"
                    className="title"
                    onClick={() => {
                      onPlay(index);
                    }}
                    disabled={!playable}
                  >
                    {track.title}
                  </button>
                  <span className="subtitle" aria-hidden>
                    {track.artist}
                  </span>
                  {!playable && <span className="why">{WHY[track.availability]}</span>}
                </div>
              </td>
              <td className="artist">{track.artist}</td>
              <td className="album">{track.album}</td>
              <td className="time">
                {formatTime(track.duration_ms === null ? undefined : track.duration_ms / 1000)}
              </td>
              <td className="actions">
                <button
                  type="button"
                  className="icon"
                  onClick={() => {
                    onPlayNext(track);
                  }}
                  disabled={!playable}
                  aria-label={`Play ${track.title} next`}
                  title="Play next"
                >
                  <QueueIcon weight="light" aria-hidden />
                </button>
                <button
                  type="button"
                  className="icon"
                  onClick={() => {
                    onAdd(track);
                  }}
                  disabled={!playable}
                  aria-label={`Add ${track.title} to the queue`}
                  title="Add to the queue"
                >
                  <ListPlusIcon weight="light" aria-hidden />
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
