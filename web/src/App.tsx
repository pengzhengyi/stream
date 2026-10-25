/**
 * @file The root component: the sign-in form, or the signed-in page.
 */

import { useEffect, useState } from "react";

import { type Account, api } from "./api";
import { Library } from "./views/Library";
import { SignIn } from "./views/SignIn";

/** Asks who is signed in, then shows the sign-in form or the Library. */
export function App() {
  const [account, setAccount] = useState<Account | null | undefined>(undefined);

  useEffect(() => {
    api.me().then(setAccount, () => {
      setAccount(null);
    });
  }, []);

  if (account === undefined) {
    return null;
  }
  if (account === null) {
    return <SignIn onSignedIn={setAccount} />;
  }
  return (
    <Library
      account={account}
      onSignedOut={() => {
        setAccount(null);
      }}
    />
  );
}
