/**
 * @file The Network section of Settings: the Mode now, its setting, and the metered networks.
 *
 * Anyone sees why medleyplay is Online or Offline and the network the server is
 * on; an admin changes the setting, marks the network the server is on metered,
 * and removes a mark.
 */

import { useEffect, useEffectEvent, useState } from "react";

import { ApiError, type Mode, type ModeSetting, type ModeSettings, api } from "../api";
import { SETTINGS, networkSaid, offlineBecause } from "../mode";

/** The Mode now, and, for an admin, its setting and the metered networks to change. */
export function NetworkSettings({
  admin,
  mode,
}: {
  readonly admin: boolean;
  readonly mode: Mode | null;
}) {
  const [settings, setSettings] = useState<ModeSettings | undefined>(undefined);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  const failed = (failure: unknown) => {
    setError(failure instanceof Error ? failure.message : String(failure));
  };
  const reload = (then = "") => {
    api.modeSettings().then((read) => {
      setSettings(read);
      setNote(then);
    }, failed);
  };
  const loadOnOpen = useEffectEvent(() => {
    reload();
  });
  useEffect(() => {
    loadOnOpen();
  }, []);

  const choose = (setting: ModeSetting) => {
    if (settings === undefined) {
      return;
    }
    setError("");
    setSettings({ ...settings, setting });
    api.saveModeSetting(setting, settings.revision).then(setSettings, (failure: unknown) => {
      if (failure instanceof ApiError && failure.status === 409) {
        reload("The setting changed elsewhere, so here it is now. Choose again to change it.");
        return;
      }
      failed(failure);
      reload();
    });
  };
  const mark = () => {
    setError("");
    api.markMetered(name.trim()).then(() => {
      setName("");
      reload("Marked.");
    }, failed);
  };
  const unmark = (id: number) => {
    setError("");
    api.unmarkMetered(id).then(() => {
      reload();
    }, failed);
  };

  const network = mode?.network ?? null;
  return (
    <>
      {error !== "" && <p role="alert">{error}</p>}
      <ModeNow mode={mode} />
      {settings === undefined ? (
        error === "" && (
          <p className="hint" aria-busy="true">
            Reading the network settings…
          </p>
        )
      ) : (
        <>
          {admin ? (
            <fieldset className="mode-setting">
              <legend>When medleyplay may contact music sites</legend>
              {SETTINGS.map(({ setting, said }) => (
                <label key={setting} className="mode-choice">
                  <input
                    type="radio"
                    name="mode-setting"
                    checked={settings.setting === setting}
                    onChange={() => {
                      choose(setting);
                    }}
                  />
                  {said}
                </label>
              ))}
            </fieldset>
          ) : (
            <p>
              {SETTINGS.find(({ setting }) => setting === settings.setting)?.said}. An admin changes
              this.
            </p>
          )}
          {admin && network !== null && network.metered_as === null && (
            <form
              className="mark-metered"
              onSubmit={(event) => {
                event.preventDefault();
                mark();
              }}
            >
              <label className="mark-name">
                Mark this network metered, as
                <input
                  type="text"
                  value={name}
                  maxLength={64}
                  required
                  placeholder={network.hotspot_like ? "Phone hotspot" : "A name, such as Office"}
                  onChange={(event) => {
                    setName(event.target.value);
                  }}
                />
              </label>
              <button type="submit" disabled={name.trim() === ""}>
                Mark metered
              </button>
              {network.hotspot_like && (
                <p className="hint">This network looks like a phone's hotspot.</p>
              )}
            </form>
          )}
          {settings.metered.length > 0 && (
            <>
              <h4>Metered networks</h4>
              <ul className="metered">
                {settings.metered.map((each) => (
                  <li key={each.id}>
                    <span>
                      {each.name} <span className="hint">{each.subnet}</span>
                    </span>
                    {admin && (
                      <button
                        type="button"
                        className="secondary outline"
                        aria-label={`Remove the mark on ${each.name}`}
                        onClick={() => {
                          unmark(each.id);
                        }}
                      >
                        Remove
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              <p className="hint">
                A phone that changes its hotspot's address is a new network until it is marked
                again.
              </p>
            </>
          )}
          <p className="hint" role="status">
            {note}
          </p>
        </>
      )}
    </>
  );
}

/** Whether medleyplay is Online or Offline and why, the network, and what waits. */
function ModeNow({ mode }: { readonly mode: Mode | null }) {
  if (mode === null) {
    return (
      <p className="hint" aria-busy="true">
        Reading the network…
      </p>
    );
  }
  const because = offlineBecause(mode);
  const waiting =
    mode.held_jobs === 1 ? "1 download waits" : `${String(mode.held_jobs)} downloads wait`;
  return (
    <div className="mode-now">
      <p>
        <strong>{because === null ? "Online" : `Offline: ${because}`}.</strong>{" "}
        {mode.online_at !== null && `Goes Online at ${timeOf(mode.online_at)} if nothing changes.`}
      </p>
      <p>{networkSaid(mode)}</p>
      {mode.held_jobs > 0 && <p className="hint">{waiting} for Online.</p>}
    </div>
  );
}

function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
