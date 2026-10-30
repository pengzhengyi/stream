/**
 * @file Editing a song's details: what each says now and where it came from, and the household's own.
 *
 * A box typed in, or a value chosen from another origin, becomes the household's
 * value, which wins; every other box shows what would show with them. Typing or
 * choosing what would show anyway drops the household's value. Saving sends only
 * what changed. Escape, Cancel, or a click outside it close it without saving, except
 * while a save is under way.
 *
 * A video's title and description, pasted, are read by the server at once as the
 * `video` origin, as a file beside the audio would be; the boxes then show what it
 * found, keeping the household's own.
 */

import { type SubmitEvent, useEffect, useRef, useState } from "react";

import type { Detail, Details, Track, VideoRead, VideoText } from "../api";
import {
  DETAIL_FIELDS,
  type DetailField,
  ORIGIN_LABELS,
  type Own,
  alternativesOf,
  boxText,
  changesOf,
  foundOf,
  ownOf,
  previewOf,
  settle,
  shownOf,
} from "../library/details";
import { Modal } from "./Modal";

/** How long text may be, as the server keeps it. */
const MAX_TEXT = 512;

/** The ranges the server keeps a number in. */
const RANGES: Partial<Record<Detail, readonly [number, number]>> = {
  track_number: [1, 999],
  disc_number: [1, 999],
  year: [1000, 2999],
};

/** How long a video's title and description may be, as the server takes them. */
const MAX_VIDEO_TITLE = 1_000;
const MAX_DESCRIPTION = 20_000;

/**
 * Edit `track`'s details, read with `load`; `onSave` sends the household's values
 * changed, `null` dropping one, and `onReadVideo` a video's pasted text.
 */
export function EditDetails({
  track,
  load,
  onSave,
  onReadVideo,
  onClose,
}: {
  readonly track: Track;
  readonly load: (trackId: number) => Promise<Details>;
  readonly onSave: (changes: Partial<Record<Detail, string | number | null>>) => Promise<void>;
  readonly onReadVideo: (text: VideoText) => Promise<VideoRead>;
  readonly onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = () => {
    dialog.current?.close();
  };
  const [details, setDetails] = useState<Details | undefined>(undefined);
  const [own, setOwn] = useState<Own>({});
  const [saving, setSaving] = useState(false);
  const [reading, setReading] = useState(false);
  const [readNote, setReadNote] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let open = true;
    load(track.id).then(
      (loaded) => {
        if (open) {
          setDetails(loaded);
          setOwn(ownOf(loaded));
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
  }, [track.id, load]);

  const save = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (details === undefined) {
      return;
    }
    const changes = changesOf(details, own);
    if (Object.keys(changes).length === 0) {
      close();
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onSave(changes);
      setSaving(false);
      close();
    } catch (failure) {
      setSaving(false);
      setError(messageOf(failure));
    }
  };
  const readVideo = async (text: VideoText) => {
    setReading(true);
    setError("");
    setReadNote("");
    try {
      const read = await onReadVideo(text);
      setDetails(read.details);
      setReadNote(
        read.songs.length > 0
          ? `Read the video's details. It lists ${String(read.songs.length)} songs.`
          : "Read the video's details.",
      );
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setReading(false);
    }
  };
  const boxes = (group: DetailField["group"]) =>
    details !== undefined &&
    DETAIL_FIELDS.filter((field) => field.group === group).map((field) => (
      <DetailBox key={field.name} field={field} details={details} own={own} onChange={setOwn} />
    ));

  return (
    <Modal
      ref={dialog}
      className="edit-details"
      labelledBy="edit-details-title"
      describedBy="edit-details-song"
      locked={saving || reading}
      onClose={onClose}
    >
      <form className="card" onSubmit={(event) => void save(event)}>
        <h2 id="edit-details-title">Edit details</h2>
        <p id="edit-details-song" className="edit-details-song">
          {track.title}
        </p>
        {details === undefined && error === "" && (
          <p className="empty" role="status">
            Reading the details…
          </p>
        )}
        {details !== undefined && (
          <>
            <PasteVideo
              read={details.video_text}
              reading={reading}
              note={readNote}
              onRead={(text) => void readVideo(text)}
            />
            <fieldset className="detail-group">
              <legend>Song</legend>
              {boxes("song")}
            </fieldset>
            <fieldset className="detail-group">
              <legend>Album</legend>
              {boxes("album")}
            </fieldset>
          </>
        )}
        {error !== "" && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <footer className="dialog-buttons">
          <button
            type="button"
            className="secondary outline dialog-button"
            disabled={saving || reading}
            onClick={close}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="dialog-button"
            disabled={details === undefined || saving || reading}
            aria-busy={saving}
          >
            Save
          </button>
        </footer>
      </form>
    </Modal>
  );
}

/** A video's title and description to paste, starting from the text `read` before. */
function PasteVideo({
  read,
  reading,
  note,
  onRead,
}: {
  readonly read: VideoText | null;
  readonly reading: boolean;
  readonly note: string;
  readonly onRead: (text: VideoText) => void;
}) {
  const [title, setTitle] = useState(read?.title ?? "");
  const [description, setDescription] = useState(read?.description ?? "");
  const empty = title.trim() === "" && description.trim() === "";
  const submit = () => {
    if (!empty && !reading) {
      onRead({ title, description });
    }
  };
  return (
    <details className="paste-video">
      <summary className="paste-video-summary">Paste the video's details</summary>
      <div className="paste-video-body">
        <label htmlFor="paste-video-title" className="detail-label">
          Video title
        </label>
        <input
          id="paste-video-title"
          className="detail-input"
          maxLength={MAX_VIDEO_TITLE}
          value={title}
          onChange={(event) => {
            setTitle(event.currentTarget.value);
          }}
          onKeyDown={(event) => {
            // Enter reads the video's details here, rather than saving the dialog.
            if (event.key === "Enter") {
              event.preventDefault();
              submit();
            }
          }}
        />
        <label htmlFor="paste-video-description" className="detail-label">
          Description
        </label>
        <textarea
          id="paste-video-description"
          className="detail-input"
          rows={5}
          maxLength={MAX_DESCRIPTION}
          value={description}
          onChange={(event) => {
            setDescription(event.currentTarget.value);
          }}
        />
        <button
          type="button"
          className="secondary paste-video-read"
          disabled={empty || reading}
          aria-busy={reading}
          onClick={submit}
        >
          Read the video's details
        </button>
        {note !== "" && (
          <p className="paste-video-note" role="status">
            {note}
          </p>
        )}
      </div>
    </details>
  );
}

/** One detail's box, where its value comes from, and what other origins say. */
function DetailBox({
  field,
  details,
  own,
  onChange,
}: {
  readonly field: DetailField;
  readonly details: Details;
  readonly own: Own;
  readonly onChange: (own: Own) => void;
}) {
  const { name, label, kind } = field;
  const id = `detail-${name}`;
  const typed = boxText(details, own, name);
  const yours = name in settle(details, own);
  const origin = originOf(details, own, field);
  const range = RANGES[name];
  return (
    <div className={`detail detail-${kind}`}>
      <label htmlFor={id} className="detail-label">
        {label}
      </label>
      <input
        id={id}
        className="detail-input"
        type={kind === "number" ? "number" : "text"}
        inputMode={kind === "number" ? "numeric" : undefined}
        min={range?.[0]}
        max={range?.[1]}
        maxLength={kind === "text" ? MAX_TEXT : undefined}
        value={typed}
        aria-describedby={origin === "" ? undefined : `${id}-origin`}
        onChange={(event) => {
          onChange({ ...own, [name]: event.currentTarget.value });
        }}
      />
      {origin !== "" && (
        <small id={`${id}-origin`} className={yours ? "detail-origin yours" : "detail-origin"}>
          {origin}
        </small>
      )}
      <div className="detail-alternatives" role="group" aria-label={`Other values for ${label}`}>
        {alternativesOf(details, name, typed).map(({ value, origin: from }) => (
          <button
            key={from}
            type="button"
            className="detail-alternative"
            aria-label={`Use “${value}”, from ${ORIGIN_LABELS[from]}`}
            onClick={() => {
              onChange({ ...own, [name]: value });
            }}
          >
            {value}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Return where `field`'s box gets its value, as the dialog says it. */
function originOf(details: Details, own: Own, field: DetailField): string {
  const { name, kind } = field;
  const shows = previewOf(details, own)[name];
  if (name in settle(details, own)) {
    if (kind === "number" && own[name]?.trim() === "") {
      return shows === undefined
        ? "Left empty"
        : `Left empty, so ${String(shows.value)} from ${ORIGIN_LABELS[shows.origin]} shows`;
    }
    return "Yours";
  }
  if (shows !== undefined) {
    return `From ${ORIGIN_LABELS[shows.origin]}`;
  }
  // An album field another origin gives, hidden because the household's album differs.
  return shownOf(foundOf(details))[name] === undefined ? "" : "Hidden, as your album differs";
}

function messageOf(failure: unknown): string {
  return failure instanceof Error ? failure.message : String(failure);
}
