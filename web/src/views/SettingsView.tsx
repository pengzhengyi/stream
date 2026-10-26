/**
 * @file Settings: how the page looks, its keyboard shortcuts, and the room Downloads may take.
 *
 * Each section saves on its own. The storage limit is the household's, so only
 * an admin changes it; a member sees it and what it holds.
 */

import { useEffect, useEffectEvent, useRef, useState } from "react";

import { ApiError, type Preview, type Settings, type Storage, api } from "../api";
import { formatBytes } from "../format";
import { ShortcutSettings } from "./ShortcutSettings";
import { ThemeSwitch } from "./ThemeSwitch";

const GB = 1_000_000_000;
/** How long after the limit stops changing its preview is asked for. */
const SETTLE_MS = 300;

/** The Settings view; `admin` may change what the household shares. */
export function SettingsView({ admin }: { readonly admin: boolean }) {
  return (
    <>
      <header className="view-heading">
        <h2 className="section">Settings</h2>
      </header>
      <section className="settings-section" aria-labelledby="appearance">
        <h3 id="appearance">Appearance</h3>
        <p className="hint">Follow this device's light or dark setting, or keep one.</p>
        <ThemeSwitch />
      </section>
      <ShortcutSettings />
      <StorageSection admin={admin} />
    </>
  );
}

/** A limit as the form holds it: none, or a number of GB as typed. */
interface Draft {
  readonly unlimited: boolean;
  readonly gb: string;
}

const draftOf = (settings: Settings): Draft =>
  settings.storage_limit === null
    ? { unlimited: true, gb: "" }
    : { unlimited: false, gb: String(Math.round((settings.storage_limit / GB) * 10) / 10) };

/** The bytes `draft` asks for, `null` for no limit, or `undefined` while it isn't a size. */
function bytesOf(draft: Draft): number | null | undefined {
  if (draft.unlimited) {
    return null;
  }
  const gb = Number(draft.gb);
  return draft.gb.trim() === "" || !Number.isFinite(gb) || gb < 0 ? undefined : Math.round(gb * GB);
}

function StorageSection({ admin }: { readonly admin: boolean }) {
  const [settings, setSettings] = useState<Settings | undefined>(undefined);
  const [storage, setStorage] = useState<Storage | undefined>(undefined);
  const [draft, setDraft] = useState<Draft>({ unlimited: true, gb: "" });
  const [preview, setPreview] = useState<Preview | undefined>(undefined);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const asking = useRef<ReturnType<typeof setTimeout>>(undefined);

  const reload = (then?: string) => {
    Promise.all([api.settings(), api.storage()]).then(
      ([read, now]) => {
        setSettings(read);
        setStorage(now);
        setDraft(draftOf(read));
        setPreview(undefined);
        setNote(then ?? "");
      },
      (failure: unknown) => {
        setError(failure instanceof Error ? failure.message : String(failure));
      },
    );
  };
  const loadOnOpen = useEffectEvent(() => {
    reload();
  });
  useEffect(() => {
    loadOnOpen();
    return () => {
      clearTimeout(asking.current);
    };
  }, []);

  const limit = bytesOf(draft);
  const changed = settings !== undefined && limit !== undefined && limit !== settings.storage_limit;

  const change = (next: Draft) => {
    setDraft(next);
    setNote("");
    setPreview(undefined);
    clearTimeout(asking.current);
    const bytes = bytesOf(next);
    if (bytes === null || bytes === undefined || bytes === settings?.storage_limit) {
      return;
    }
    asking.current = setTimeout(() => {
      api.storage(bytes).then(
        (planned) => {
          setPreview(planned.preview ?? undefined);
        },
        () => {
          // Without a preview, saving still works; the policy says what it removed.
        },
      );
    }, SETTLE_MS);
  };

  const save = () => {
    if (settings === undefined || limit === undefined) {
      return;
    }
    setError("");
    api.saveSettings({ ...settings, storage_limit: limit }).then(
      () => {
        reload("Saved.");
      },
      (failure: unknown) => {
        if (failure instanceof ApiError && failure.status === 409) {
          reload(
            "These settings changed elsewhere, so here they are now. Change them again to save.",
          );
          return;
        }
        setError(failure instanceof Error ? failure.message : String(failure));
      },
    );
  };

  return (
    <section className="settings-section" aria-labelledby="storage">
      <h3 id="storage">Downloads and storage</h3>
      {error !== "" && <p role="alert">{error}</p>}
      {storage === undefined || settings === undefined ? (
        error === "" && (
          <p className="hint" aria-busy="true">
            Reading what the Downloads hold…
          </p>
        )
      ) : (
        <>
          <Usage storage={storage} />
          {admin ? (
            <form
              className="limit"
              onSubmit={(event) => {
                event.preventDefault();
                save();
              }}
            >
              <fieldset>
                <legend>Storage limit</legend>
                <label className="limit-choice">
                  <input
                    type="radio"
                    name="limit"
                    checked={draft.unlimited}
                    onChange={() => {
                      change({ ...draft, unlimited: true });
                    }}
                  />
                  No limit
                </label>
                <label className="limit-choice">
                  <input
                    type="radio"
                    name="limit"
                    checked={!draft.unlimited}
                    onChange={() => {
                      change({ unlimited: false, gb: draft.gb === "" ? "20" : draft.gb });
                    }}
                  />
                  Up to
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step={0.5}
                    aria-label="Limit in GB"
                    value={draft.gb}
                    disabled={draft.unlimited}
                    onChange={(event) => {
                      change({ unlimited: false, gb: event.currentTarget.value });
                    }}
                  />
                  GB
                </label>
              </fieldset>
              <p className="hint" role="status">
                {limit === undefined
                  ? "Type a size in GB, such as 20."
                  : changed && limit !== null
                    ? previewText(preview)
                    : ""}
              </p>
              <button type="submit" disabled={!changed}>
                Save
              </button>
              {note !== "" && <p className="hint saved">{note}</p>}
            </form>
          ) : (
            <p className="hint">
              {settings.storage_limit === null
                ? "There is no storage limit. An admin can set one."
                : `The storage limit is ${formatBytes(settings.storage_limit)}, set by an admin.`}
            </p>
          )}
          <p className="hint">
            When room is needed, the Downloads of the least favorite songs go first; a song a kept
            Playlist holds is never removed to make room.
          </p>
        </>
      )}
    </section>
  );
}

/** What the Downloads and cache use, against the limit or the disk. */
function Usage({ storage }: { readonly storage: Storage }) {
  if (storage.error !== null) {
    return <p role="alert">{storage.error}</p>;
  }
  const downloads = storage.downloads ?? 0;
  const cache = storage.cache ?? 0;
  const reserved = storage.reserved ?? 0;
  const used = downloads + cache + reserved;
  const room = storage.limit ?? used + (storage.free ?? 0);
  const share = (bytes: number) => `${String(room > 0 ? Math.min((bytes / room) * 100, 100) : 0)}%`;
  const last = storage.last_evaluation;
  return (
    <div className="usage">
      <p className="usage-total">
        <strong>{formatBytes(used)}</strong>{" "}
        {storage.limit === null
          ? `used, ${formatBytes(storage.free ?? 0)} free on this disk`
          : `of ${formatBytes(storage.limit)} used`}
      </p>
      <div className="meter" aria-hidden>
        <span className="downloads" style={{ width: share(downloads) }} />
        <span className="cache" style={{ width: share(cache) }} />
        <span className="reserved" style={{ width: share(reserved) }} />
      </div>
      <dl className="legend">
        <div>
          <dt>
            <span className="swatch downloads" aria-hidden />
            Downloads
          </dt>
          <dd>{formatBytes(downloads)}</dd>
        </div>
        <div>
          <dt>
            <span className="swatch cache" aria-hidden />
            Prepared copies
          </dt>
          <dd>{formatBytes(cache)}</dd>
        </div>
        {reserved > 0 && (
          <div>
            <dt>
              <span className="swatch reserved" aria-hidden />
              Downloading
            </dt>
            <dd>{formatBytes(reserved)}</dd>
          </div>
        )}
        {storage.wanted !== null && (
          <div>
            <dt>Kept Playlists want</dt>
            <dd>{formatBytes(storage.wanted)}</dd>
          </div>
        )}
      </dl>
      {last !== null && (
        <p className="hint">
          Last checked {new Date(last.at).toLocaleString()}: {countOf(last.removed, "removed")},{" "}
          {countOf(last.started, "started")}.{last.error === null ? "" : ` ${last.error}`}
        </p>
      )}
    </div>
  );
}

const countOf = (count: number, done: string) =>
  `${String(count)} ${count === 1 ? "download" : "downloads"} ${done}`;

/** Say what saving a lower limit would remove, from its preview. */
function previewText(preview: Preview | undefined): string {
  if (preview === undefined) {
    return "Working out what this limit would remove…";
  }
  const downloads = preview.removals.filter((each) => each.kind === "download");
  const copies = preview.removals.filter((each) => each.kind === "cache");
  if (downloads.length === 0 && copies.length === 0) {
    return "Nothing needs removing to fit.";
  }
  const sized = (items: typeof downloads, one: string, many: string) =>
    `${String(items.length)} ${items.length === 1 ? one : many} (${formatBytes(
      items.reduce((total, each) => total + each.size, 0),
    )})`;
  const parts = [
    downloads.length > 0 ? sized(downloads, "download", "downloads") : "",
    copies.length > 0 ? sized(copies, "prepared copy", "prepared copies") : "",
  ].filter(Boolean);
  return `Saving removes ${parts.join(" and ")} to fit.`;
}
