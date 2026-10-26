/**
 * @file Adding a song to Playlists: choose one or several, or name a new one.
 *
 * Escape, Cancel, or a click outside it close it without adding anything; a new
 * Playlist is made only when the song is added.
 */

import { PlusIcon } from "@phosphor-icons/react";
import { type SubmitEvent, useRef, useState } from "react";

import type { Playlist, Track } from "../api";
import { Modal } from "./Modal";

/** Choose Playlists for `track`; `onSave` adds it to the ids chosen and to new Playlists by name. */
export function AddToPlaylist({
  track,
  playlists,
  onSave,
  onClose,
}: {
  readonly track: Track;
  readonly playlists: readonly Playlist[];
  readonly onSave: (ids: readonly string[], newNames: readonly string[]) => Promise<void>;
  readonly onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = () => {
    dialog.current?.close();
  };
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
  const [newNames, setNewNames] = useState<readonly string[]>([]);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  // Only plain Playlists take a song; Favorites follows the hearts, a smart one its rules.
  const own = playlists.filter((playlist) => playlist.builtin === null && playlist.rules === null);
  const count = chosen.size + newNames.length;

  const choose = (id: string, on: boolean) => {
    setChosen((now) => {
      const next = new Set(now);
      if (on) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  };
  const addName = () => {
    const trimmed = name.trim();
    if (trimmed !== "") {
      setNewNames((now) => [...now, trimmed]);
      setName("");
    }
  };
  const save = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await onSave([...chosen], newNames);
      close();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      ref={dialog}
      className="add-to-playlist"
      labelledBy="add-to-playlist-title"
      onClose={onClose}
    >
      <form className="card" onSubmit={(event) => void save(event)}>
        <h2 id="add-to-playlist-title">Add “{track.title}” to playlists</h2>
        {own.length === 0 && newNames.length === 0 && (
          <p className="empty">No playlists yet. Name one below to make it.</p>
        )}
        <ul className="choices">
          {own.map((playlist) => {
            const holds = playlist.track_ids.includes(track.id);
            return (
              <li key={playlist.id} className="choice">
                <label className="choice-label">
                  <input
                    type="checkbox"
                    className="choice-box"
                    checked={holds || chosen.has(playlist.id)}
                    disabled={holds}
                    onChange={(event) => {
                      choose(playlist.id, event.currentTarget.checked);
                    }}
                  />
                  <span className="choice-name">{playlist.name}</span>
                  <span className="choice-meta">
                    {holds ? "Already added" : songsOf(playlist.track_ids.length)}
                  </span>
                </label>
              </li>
            );
          })}
          {newNames.map((newName, index) => (
            <li key={`new-${String(index)}`} className="choice">
              <label className="choice-label">
                <input
                  type="checkbox"
                  className="choice-box"
                  checked
                  onChange={() => {
                    setNewNames((now) => now.filter((_, i) => i !== index));
                  }}
                />
                <span className="choice-name">{newName}</span>
                <span className="choice-meta">New</span>
              </label>
            </li>
          ))}
        </ul>
        <div className="new-playlist">
          <input
            type="text"
            className="new-playlist-name"
            aria-label="New playlist"
            placeholder="New playlist"
            value={name}
            maxLength={128}
            onChange={(event) => {
              setName(event.currentTarget.value);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addName();
              }
            }}
          />
          <button
            type="button"
            className="secondary dialog-button"
            onClick={addName}
            disabled={name.trim() === ""}
          >
            <PlusIcon weight="bold" aria-hidden />
            Make
          </button>
        </div>
        {error !== "" && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <footer className="dialog-buttons">
          <button type="button" className="secondary outline dialog-button" onClick={close}>
            Cancel
          </button>
          <button
            type="submit"
            className="dialog-button"
            disabled={count === 0 || saving}
            aria-busy={saving}
          >
            {count === 0
              ? "Add"
              : `Add to ${count === 1 ? "1 playlist" : `${String(count)} playlists`}`}
          </button>
        </footer>
      </form>
    </Modal>
  );
}

function songsOf(count: number): string {
  return count === 1 ? "1 song" : `${String(count)} songs`;
}
