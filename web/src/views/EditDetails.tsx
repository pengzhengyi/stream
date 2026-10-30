/**
 * @file Editing a song's details: what each says now and where it came from, and the household's own.
 *
 * A box typed in, or a value chosen from another origin, becomes the household's
 * value, which wins; every other box shows what would show with them. Typing or
 * choosing what would show anyway drops the household's value. Saving sends only
 * what changed. Escape, Cancel, or a click outside it close it without saving, except
 * while a save is under way.
 */

import { type SubmitEvent, useEffect, useRef, useState } from "react";

import type { Detail, Details, Track } from "../api";
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

/**
 * Edit `track`'s details, read with `load`; `onSave` sends the household's values
 * changed, `null` dropping one.
 */
export function EditDetails({
  track,
  load,
  onSave,
  onClose,
}: {
  readonly track: Track;
  readonly load: (trackId: number) => Promise<Details>;
  readonly onSave: (changes: Partial<Record<Detail, string | number | null>>) => Promise<void>;
  readonly onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = () => {
    dialog.current?.close();
  };
  const [details, setDetails] = useState<Details | undefined>(undefined);
  const [own, setOwn] = useState<Own>({});
  const [saving, setSaving] = useState(false);
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
      locked={saving}
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
            disabled={saving}
            onClick={close}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="dialog-button"
            disabled={details === undefined || saving}
            aria-busy={saving}
          >
            Save
          </button>
        </footer>
      </form>
    </Modal>
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
