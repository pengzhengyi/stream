/**
 * @file Splitting one long file into its songs, or editing the songs it is split into.
 *
 * A row per song: where it starts, its title, and its artist. Rows can be added,
 * removed, and moved, filled from a song list found in the video's details, or
 * read from a pasted list. A row keeps its song by id, so a song moved, renamed, or
 * retimed keeps its ratings and plays; saving says first how many songs it would
 * remove with theirs, and so does unsplitting.
 */

import { ArrowDownIcon, ArrowUpIcon, PlusIcon, TrashIcon } from "@phosphor-icons/react";
import { type SubmitEvent, useEffect, useRef, useState } from "react";

import type { Song, SongRowIn, Songs, Track } from "../api";
import { newId } from "../ids";
import { formatStart, parseStart } from "../library/songTimes";
import { Modal } from "./Modal";

/** A row as the editor holds it: the start as typed, and the song it keeps, if any. */
interface Row {
  readonly key: string;
  readonly id: number | null;
  readonly start: string;
  readonly title: string;
  readonly artist: string;
}

/**
 * Edit the songs `album`'s file is split into, read with `load`; `onSave` sends the
 * rows, `readList` reads a pasted list, and `onUnsplit` removes every song.
 */
export function EditSongs({
  album,
  load,
  readList,
  onSave,
  onUnsplit,
  onClose,
}: {
  readonly album: Track;
  readonly load: (trackId: number) => Promise<Songs>;
  readonly readList: (trackId: number, text: string) => Promise<readonly Song[]>;
  readonly onSave: (rows: readonly SongRowIn[]) => Promise<void>;
  readonly onUnsplit: () => Promise<void>;
  readonly onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = () => {
    dialog.current?.close();
  };
  const [songs, setSongs] = useState<Songs | undefined>(undefined);
  const [rows, setRows] = useState<readonly Row[]>([]);
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Set once saving or unsplitting has said what it removes, so the next press goes ahead.
  const [confirming, setConfirming] = useState<"save" | "unsplit" | undefined>(undefined);

  useEffect(() => {
    let open = true;
    load(album.id).then(
      (loaded) => {
        if (open) {
          setSongs(loaded);
          setRows(loaded.songs.map((song) => rowOf(song, song.id)));
        }
      },
      (failure: unknown) => {
        if (open) {
          setError(messageOf(failure));
        }
      },
    );
    return () => {
      open = false;
    };
  }, [album.id, load]);

  const edit = (next: readonly Row[]) => {
    setRows(next);
    setConfirming(undefined);
    setError("");
  };
  const change = (key: string, field: "start" | "title" | "artist", value: string) => {
    edit(rows.map((row) => (row.key === key ? { ...row, [field]: value } : row)));
  };
  const move = (from: number, to: number) => {
    const next = [...rows];
    const [moving] = next.splice(from, 1);
    if (moving !== undefined) {
      next.splice(to, 0, moving);
      edit(next);
    }
  };
  // A list found or pasted starts over: its songs are new, and the rows' songs go.
  const startFrom = (list: readonly Song[]) => {
    edit(list.map((song) => rowOf(song, null)));
  };
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  };

  const split = (songs?.songs.length ?? 0) > 0;
  const kept = new Set(rows.flatMap((row) => (row.id === null ? [] : [row.id])));
  const removing = songs?.songs.filter((song) => !kept.has(song.id)).length ?? 0;

  const save = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    const sent = rowsIn(rows);
    if (typeof sent === "string") {
      setError(sent);
      return;
    }
    if (removing > 0 && confirming !== "save") {
      setConfirming("save");
      return;
    }
    void run(async () => {
      await onSave(sent);
      close();
    });
  };
  const unsplit = () => {
    if (confirming !== "unsplit") {
      setConfirming("unsplit");
      return;
    }
    void run(async () => {
      await onUnsplit();
      close();
    });
  };

  return (
    <Modal
      ref={dialog}
      className="edit-songs"
      labelledBy="edit-songs-title"
      describedBy="edit-songs-file"
      locked={busy}
      onClose={onClose}
    >
      <form className="card" onSubmit={save}>
        <h2 id="edit-songs-title">{split ? "Edit songs" : "Split into songs"}</h2>
        <p id="edit-songs-file" className="edit-details-song">
          {album.title}
        </p>
        {songs === undefined && error === "" && (
          <p className="empty" role="status">
            Reading the songs…
          </p>
        )}
        {songs !== undefined && (
          <>
            {songs.needs_check && (
              <p className="songs-note">
                The file's length changed since it was split; check where each song starts.
              </p>
            )}
            {songs.found.map((list, index) => (
              <button
                key={index}
                type="button"
                className="secondary outline songs-found"
                disabled={busy}
                onClick={() => {
                  startFrom(list);
                }}
              >
                {`Use the ${String(list.length)} songs from the video's details`}
              </button>
            ))}
            <details className="paste-video">
              <summary className="paste-video-summary">Paste a list</summary>
              <div className="paste-video-body">
                <label htmlFor="songs-list" className="detail-label">
                  Song list
                </label>
                <textarea
                  id="songs-list"
                  className="detail-input"
                  rows={5}
                  placeholder={"00:00 Intro\n03:12 Night Drive - Blue Room"}
                  value={pasted}
                  onChange={(event) => {
                    setPasted(event.currentTarget.value);
                  }}
                />
                <button
                  type="button"
                  className="secondary paste-video-read"
                  disabled={busy || pasted.trim() === ""}
                  onClick={() =>
                    void run(async () => {
                      startFrom(await readList(album.id, pasted));
                    })
                  }
                >
                  Read the list
                </button>
              </div>
            </details>
            <ol className="song-rows">
              {rows.map((row, index) => (
                <SongRow
                  key={row.key}
                  row={row}
                  place={index + 1}
                  first={index === 0}
                  last={index === rows.length - 1}
                  onChange={(field, value) => {
                    change(row.key, field, value);
                  }}
                  onMove={(by) => {
                    move(index, index + by);
                  }}
                  onRemove={() => {
                    edit(rows.filter((each) => each.key !== row.key));
                  }}
                />
              ))}
            </ol>
            <button
              type="button"
              className="secondary outline songs-add"
              onClick={() => {
                edit([...rows, { key: newId(), id: null, start: "", title: "", artist: "" }]);
              }}
            >
              <PlusIcon aria-hidden /> Add a song
            </button>
          </>
        )}
        {confirming !== undefined && (
          <p className="songs-note" role="status">
            {confirming === "save"
              ? `Saving removes ${songCount(removing)}, with their ratings and plays.`
              : `Unsplitting removes ${songCount(songs?.songs.length ?? 0)}, with their ratings and plays.`}
          </p>
        )}
        {error !== "" && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <footer className="dialog-buttons">
          {split && (
            <button
              type="button"
              className="secondary outline dialog-button songs-unsplit"
              disabled={busy}
              onClick={unsplit}
            >
              {confirming === "unsplit"
                ? `Unsplit and remove ${songCount(songs?.songs.length ?? 0)}`
                : "Unsplit"}
            </button>
          )}
          <button
            type="button"
            className="secondary outline dialog-button"
            disabled={busy}
            onClick={close}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="dialog-button"
            disabled={songs === undefined || busy}
            aria-busy={busy}
          >
            {confirming === "save" ? `Save and remove ${songCount(removing)}` : "Save"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}

/** One song's row: its start, title, and artist, and buttons to move or remove it. */
function SongRow({
  row,
  place,
  first,
  last,
  onChange,
  onMove,
  onRemove,
}: {
  readonly row: Row;
  readonly place: number;
  readonly first: boolean;
  readonly last: boolean;
  readonly onChange: (field: "start" | "title" | "artist", value: string) => void;
  readonly onMove: (by: -1 | 1) => void;
  readonly onRemove: () => void;
}) {
  const named = row.title.trim() === "" ? `song ${String(place)}` : `“${row.title}”`;
  return (
    <li className="song-row">
      <input
        className="detail-input song-start"
        aria-label={`Start of song ${String(place)}`}
        inputMode="numeric"
        placeholder="0:00"
        value={row.start}
        onChange={(event) => {
          onChange("start", event.currentTarget.value);
        }}
      />
      <input
        className="detail-input song-title"
        aria-label={`Title of song ${String(place)}`}
        value={row.title}
        onChange={(event) => {
          onChange("title", event.currentTarget.value);
        }}
      />
      <input
        className="detail-input song-artist"
        aria-label={`Artist of song ${String(place)}`}
        placeholder="Artist"
        value={row.artist}
        onChange={(event) => {
          onChange("artist", event.currentTarget.value);
        }}
      />
      <span className="song-row-buttons">
        <button
          type="button"
          className="icon"
          aria-label={`Move ${named} up`}
          disabled={first}
          onClick={() => {
            onMove(-1);
          }}
        >
          <ArrowUpIcon aria-hidden />
        </button>
        <button
          type="button"
          className="icon"
          aria-label={`Move ${named} down`}
          disabled={last}
          onClick={() => {
            onMove(1);
          }}
        >
          <ArrowDownIcon aria-hidden />
        </button>
        <button type="button" className="icon" aria-label={`Remove ${named}`} onClick={onRemove}>
          <TrashIcon aria-hidden />
        </button>
      </span>
    </li>
  );
}

function rowOf(song: Song, id: number | null): Row {
  return {
    key: newId(),
    id,
    start: formatStart(song.start_ms),
    title: song.title,
    artist: song.artist,
  };
}

/** Return the rows as the server takes them, or why one can't be. */
function rowsIn(rows: readonly Row[]): SongRowIn[] | string {
  const sent: SongRowIn[] = [];
  for (const [index, row] of rows.entries()) {
    const start = parseStart(row.start);
    if (start === undefined) {
      return `Song ${String(index + 1)} starts at no time; write it as 3:12 or 1:07:40.`;
    }
    sent.push({ id: row.id, start_ms: start, title: row.title.trim(), artist: row.artist.trim() });
  }
  return sent;
}

function songCount(count: number): string {
  return count === 1 ? "1 song" : `${String(count)} songs`;
}

function messageOf(failure: unknown): string {
  return failure instanceof Error ? failure.message : String(failure);
}
