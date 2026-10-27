import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { ALICE, modeOf, serve, signedIn, trackOf } from "./testing/server";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows the Library to a signed-in browser", async () => {
    serve(signedIn([trackOf(1, "Night Drive")]));

    render(<App />);

    expect(await screen.findByRole("button", { name: "Night Drive" })).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("says in the header when medleyplay is Offline, and why, leading to Settings", async () => {
    serve({
      ...signedIn([trackOf(1, "Night Drive")]),
      "GET /api/mode": { body: modeOf({ online: false, reason: "no_network", network: null }) },
    });

    render(<App />);

    const note = await screen.findByRole("link", { name: "Offline: no network" });
    expect(note).toHaveAttribute("href", "#/settings");
  });

  it("says nothing in the header while medleyplay is Online", async () => {
    serve(signedIn([trackOf(1, "Night Drive")]));

    render(<App />);

    expect(await screen.findByRole("button", { name: "Night Drive" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Offline/ })).not.toBeInTheDocument();
  });

  it("asks a signed-out browser to sign in, then shows the Library", async () => {
    serve({
      "GET /api/me": { status: 401, body: { detail: "Sign in first." } },
      "GET /api/setup": { body: { set_up: true, multiple_accounts: false } },
      "POST /api/session": (body) =>
        JSON.stringify(body) === JSON.stringify({ username: "alice", password: "secret words" })
          ? { body: ALICE }
          : { status: 401, body: { detail: "The username or password is wrong." } },
      "GET /api/tracks": { body: [trackOf(1, "Night Drive")] },
    });
    render(<App />);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "secret words");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("button", { name: "Night Drive" })).toBeInTheDocument();
  });

  it("returns to the sign-in form after signing out", async () => {
    serve({
      ...signedIn([]),
      "DELETE /api/session": { status: 204 },
      "GET /api/setup": { body: { set_up: true, multiple_accounts: false } },
    });
    render(<App />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("form", { name: "Sign in" })).toBeInTheDocument();
  });
});
