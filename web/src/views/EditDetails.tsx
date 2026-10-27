/**
 * @file Editing a song's details: what each says now and where it came from, and the household's own.
 *
 * Each box starts with what shows. A box changed from what was found is the
 * household's value, which wins; choosing what another origin says is one click.
 * Escape, Cancel, or a click outside it close it without saving.
 */

import { type SubmitEvent, useEffect, useRef, useState } from "react";

import type { Detail, Details, Track } from "../api";
import {
  DETAIL_FIELDS,
  type DetailField,
  type Inputs,
  ORIGIN_LABELS,
  alternativesOf,
  foundText,
  householdOf,
  inputsOf,
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

/** Edit `track`'s details, read with `load`; `onSave` makes the edits the household's values. */
export function EditDetails({
  track,
  load,
  onSave,
  onClose,
}: {
  readonly track: Track;
  readonly load: (trackId: number) => Promise<Details>;
  readonly onSave: (values: Partial<Record<Detail, string | number>>) => Promise<void>;
  readonly onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = () => {
    dialog.current?.close();
  };
  const [details, setDetails] = useState<Details | undefined>(undefined);
  const [inputs, setInputs] = useState<Inputs | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let open = true;
    load(track.id).then(
      (loaded) => {
        if (open) {
          setDetails(loaded);
          setInputs(inputsOf(loaded));
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
    if (details === undefined || inputs === undefined) {
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onSave(householdOf(details, inputs));
      close();
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setSaving(false);
    }
  };
  const fieldsOf = (group: DetailField["group"]) =>
    details !== undefined &&
    inputs !== undefined &&
    DETAIL_FIELDS.filter((field) => field.group === group).map((field) => (
      <DetailBox
        key={field.name}
        field={field}
        details={details}
        typed={inputs[field.name]}
        onChange={(value) => {
          setInputs((now) => now && { ...now, [field.name]: value });
        }}
      />
    ));

  return (
    <Modal ref={dialog} className="edit-details" labelledBy="edit-details-title" onClose={onClose}>
      <form className="card" onSubmit={(event) => void save(event)}>
        <h2 id="edit-details-title">Edit details</h2>
        <p className="edit-details-song">{track.title}</p>
        {details === undefined && error === "" && <p className="empty">Reading the details…</p>}
        {details !== undefined && (
          <>
            <fieldset className="detail-group">
              <legend>Song</legend>
              {fieldsOf("song")}
            </fieldset>
            <fieldset className="detail-group">
              <legend>Album</legend>
              {fieldsOf("album")}
            </fieldset>
          </>
        )}
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

/** One detail's box, where its value came from, and what other origins say. */
function DetailBox({
  field,
  details,
  typed,
  onChange,
}: {
  readonly field: DetailField;
  readonly details: Details;
  readonly typed: string;
  readonly onChange: (value: string) => void;
}) {
  const { name, label, kind } = field;
  const id = `detail-${name}`;
  const found = details.found[name];
  const yours = typed.trim() !== foundText(details, name);
  const origin = yours ? "Yours" : found === undefined ? "" : `From ${ORIGIN_LABELS[found.origin]}`;
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
          onChange(event.currentTarget.value);
        }}
      />
      {origin !== "" && (
        <small id={`${id}-origin`} className={yours ? "detail-origin yours" : "detail-origin"}>
          {origin}
        </small>
      )}
      <div className="detail-alternatives">
        {alternativesOf(details, name, typed).map(({ value, origin: from }) => (
          <button
            key={from}
            type="button"
            className="detail-alternative"
            aria-label={`Use “${value}”, from ${ORIGIN_LABELS[from]}`}
            title={`From ${ORIGIN_LABELS[from]}`}
            onClick={() => {
              onChange(value);
            }}
          >
            {value}
          </button>
        ))}
      </div>
    </div>
  );
}

function messageOf(failure: unknown): string {
  return failure instanceof Error ? failure.message : String(failure);
}
