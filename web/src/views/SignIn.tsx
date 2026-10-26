/**
 * @file Signing in, or creating the first Account on a new server.
 */

import { WaveformIcon } from "@phosphor-icons/react";
import { type SubmitEvent, useEffect, useState } from "react";

import { type Account, api } from "../api";

/** The sign-in form; on a server with no Accounts yet, the form that creates the admin. */
export function SignIn({ onSignedIn }: { readonly onSignedIn: (account: Account) => void }) {
  const [setUp, setSetUp] = useState<boolean | undefined>(undefined);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.setupStatus().then(
      (status) => {
        setSetUp(status.set_up);
      },
      () => {
        setError("The server can't be reached.");
      },
    );
  }, []);

  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const field = (name: string) => {
      const value = form.get(name);
      return typeof value === "string" ? value : "";
    };
    setBusy(true);
    setError("");
    const signingIn =
      setUp === false
        ? api.setUp(field("username"), field("display_name"), field("password"))
        : api.signIn(field("username"), field("password"));
    signingIn.then(onSignedIn, (failure: unknown) => {
      setError(failure instanceof Error ? failure.message : String(failure));
      setBusy(false);
    });
  };

  if (setUp === undefined && error === "") {
    return null;
  }
  const firstRun = setUp === false;
  return (
    <main className="sign-in">
      <h1>
        <WaveformIcon weight="bold" aria-hidden />
        medleyplay
      </h1>
      <form onSubmit={submit} aria-label={firstRun ? "Create the admin Account" : "Sign in"}>
        {firstRun && <p>Create the first Account. It is the admin.</p>}
        <label>
          Username
          <input name="username" autoComplete="username" required />
        </label>
        {firstRun && (
          <label>
            Display name
            <input name="display_name" autoComplete="name" required />
          </label>
        )}
        <label>
          Password
          <input
            name="password"
            type="password"
            autoComplete={firstRun ? "new-password" : "current-password"}
            required
          />
        </label>
        {error !== "" && <p role="alert">{error}</p>}
        <button type="submit" disabled={busy}>
          {firstRun ? "Create Account" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
