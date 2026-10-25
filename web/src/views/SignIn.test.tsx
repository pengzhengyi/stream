import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ALICE, serve } from "../testing/server";
import { SignIn } from "./SignIn";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SignIn", () => {
  it("creates the admin on a server with no Accounts yet", async () => {
    const created: unknown[] = [];
    serve({
      "GET /api/setup": { body: { set_up: false, multiple_accounts: false } },
      "POST /api/setup": (body) => {
        created.push(body);
        return { status: 201, body: ALICE };
      },
    });
    const onSignedIn = vi.fn();
    render(<SignIn onSignedIn={onSignedIn} />);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Display name"), "Alice");
    await user.type(screen.getByLabelText("Password"), "secret words");
    await user.click(screen.getByRole("button", { name: "Create Account" }));

    await vi.waitFor(() => {
      expect(onSignedIn).toHaveBeenCalledWith(ALICE);
    });
    expect(created).toEqual([
      { username: "alice", display_name: "Alice", password: "secret words" },
    ]);
  });

  it("says why a sign-in was refused", async () => {
    serve({
      "GET /api/setup": { body: { set_up: true, multiple_accounts: false } },
      "POST /api/session": { status: 401, body: { detail: "The username or password is wrong." } },
    });
    render(<SignIn onSignedIn={vi.fn()} />);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The username or password is wrong.",
    );
  });

  it("says when the server can't be reached", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));

    render(<SignIn onSignedIn={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("The server can't be reached.");
  });
});
