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
  const [readError, setReadError] = useState("");
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
    setReadError("");
    setReadNote("");
    try {
      const read = await onReadVideo(text);
      setDetails(read.details);
      setReadNote(noteOf(read));
    } catch (failure) {
      setReadError(messageOf(failure));
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
              busy={saving || reading}
              reading={reading}
              note={readNote}
              error={readError}
              onEdit={() => {
                setReadNote("");
                setReadError("");
              }}
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

/**
 * A video's title and description to paste, starting from the text `read` before;
 * it can't be read while the dialog is `busy` saving or reading.
 */
function PasteVideo({
  read,
  busy,
  reading,
  note,
  error,
  onEdit,
  onRead,
}: {
  readonly read: VideoText | null;
  readonly busy: boolean;
  readonly reading: boolean;
  readonly note: string;
  readonly error: string;
  readonly onEdit: () => void;
  readonly onRead: (text: VideoText) => void;
}) {
  const [title, setTitle] = useState(read?.title ?? "");
  const [description, setDescription] = useState(read?.description ?? "");
  const empty = title.trim() === "" && description.trim() === "";
  const submit = () => {
    if (!empty && !busy) {
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
            onEdit();
          }}
          onKeyDown={(event) => {
            // Enter reads the video's details here, rather than saving the dialog; an
            // Enter that ends composing a word, as in Japanese, only ends it.
            if (event.key === "Enter" && !event.nativeEvent.isComposing) {
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
            onEdit();
          }}
        />
        <small className="paste-video-hint">
          Reading replaces what the video said before; your own values stay.
        </small>
        <button
          type="button"
          className="secondary paste-video-read"
          disabled={empty || busy}
          aria-busy={reading}
          onClick={submit}
        >
          Read the video's details
        </button>
        <p className="paste-video-note" role="status">
          {note}
        </p>
        {error !== "" && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
    </details>
  );
}

const LIST = new Intl.ListFormat("en", { style: "long", type: "conjunction" });

/** Say what reading a video's text found: the details it gave, and how many songs it lists. */
function noteOf(read: VideoRead): string {
  const video = read.details.origins.video ?? {};
  const found = DETAIL_FIELDS.filter(({ name }) => video[name] !== undefined).map(({ label }) =>
    label.toLowerCase(),
  );
  const songs = read.songs.length > 0 ? ` It lists ${String(read.songs.length)} songs.` : "";
  return found.length > 0
    ? `Read the video's details: ${LIST.format(found)}.${songs}`
    : `Read the video's details, but found no details in them.${songs}`;
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
