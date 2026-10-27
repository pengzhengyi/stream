import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MeteredNetwork, Mode, Settings, Storage } from "../api";
import { type Routes, modeOf, modeSettingsOf, serve } from "../testing/server";
import { SettingsView } from "./SettingsView";

const GB = 1_000_000_000;

/** A limit of 20 GB, saved twice before, so at revision 2. */
const LIMIT_20: Settings = { storage_limit: 20 * GB, removal_order: "least_favorite", revision: 2 };

/** 1.5 GB of Downloads and 0.5 GB of prepared copies, under a 20 GB limit. */
const USING_2: Storage = {
  limit: 20 * GB,
  downloads: 1.5 * GB,
  cache: 0.5 * GB,
  reserved: 0,
  free: 100 * GB,
  disk_size: 500 * GB,
  wanted: 1.2 * GB,
  last_evaluation: null,
  error: null,
  preview: null,
};

function open(
  admin: boolean,
  routes: Routes = {},
  mode: Mode = modeOf(),
  metered: readonly MeteredNetwork[] = [],
) {
  const served = serve({
    "GET /api/settings": { body: LIMIT_20 },
    "GET /api/storage": { body: USING_2 },
    ...modeSettingsOf(mode, metered),
    ...routes,
  });
  render(<SettingsView admin={admin} mode={mode} />);
  return served;
}

/** The server on an iPhone hotspot an admin marked metered, so Offline. */
const ON_THE_HOTSPOT = modeOf({
  online: false,
  reason: "metered",
  network: { kind: "wifi", metered_as: "iPhone hotspot", hotspot_like: true },
});

const HOTSPOT_MARK: MeteredNetwork = {
  id: 1,
  name: "iPhone hotspot",
  subnet: "172.20.10.0/28",
  hotspot_like: true,
};

const network = () => within(screen.getByRole("region", { name: "Network" }));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("storage settings", () => {
  it("shows what the Downloads and prepared copies use against the limit", async () => {
    open(false);

    expect(await screen.findByText(/of 20 GB used/)).toHaveTextContent("2 GB of 20 GB used");
    expect(screen.getByText("1.5 GB")).toBeInTheDocument();
    expect(screen.getByText("500 MB")).toBeInTheDocument();
    expect(screen.getByText("1.2 GB")).toBeInTheDocument();
  });

  it("tells a member the limit an admin set, with nothing to change", async () => {
    open(false);

    expect(
      await screen.findByText("The storage limit is 20 GB, set by an admin."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });

  it("previews what a lower limit removes, then saves it at the revision read", async () => {
    const sent: unknown[] = [];
    open(true, {
      "GET /api/storage?limit=1000000000": {
        body: {
          ...USING_2,
          preview: {
            removals: [
              { kind: "download", size: 400_000_000 },
              { kind: "download", size: 200_000_000 },
              { kind: "cache", size: 80_000_000 },
            ],
          },
        },
      },
      "PUT /api/settings": (body) => {
        sent.push(body);
        return { body: { ...LIMIT_20, storage_limit: GB, revision: 3 } };
      },
    });
    const size = await screen.findByRole("spinbutton", { name: "Limit in GB" });

    await userEvent.clear(size);
    await userEvent.type(size, "1");

    expect(
      await screen.findByText(
        "Saving removes 2 downloads (600 MB) and 1 prepared copy (80 MB) to fit.",
      ),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(sent).toEqual([{ storage_limit: GB, removal_order: "least_favorite", revision: 2 }]);
  });

  it("saves no limit at all", async () => {
    const sent: unknown[] = [];
    open(true, {
      "PUT /api/settings": (body) => {
        sent.push(body);
        return { body: { ...LIMIT_20, storage_limit: null, revision: 3 } };
      },
    });

    await userEvent.click(await screen.findByRole("radio", { name: "No limit" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(sent).toEqual([{ storage_limit: null, removal_order: "least_favorite", revision: 2 }]);
    });
  });

  it("shows the settings as they are now when someone else saved first", async () => {
    open(true, {
      "PUT /api/settings": { status: 409, body: { detail: "The settings changed." } },
    });
    await userEvent.click(await screen.findByRole("radio", { name: "No limit" }));

    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/These settings changed elsewhere/)).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "Limit in GB" })).toHaveValue(20);
  });

  it("can't save a size that isn't one", async () => {
    open(true);
    const size = await screen.findByRole("spinbutton", { name: "Limit in GB" });

    await userEvent.clear(size);

    expect(screen.getByText("Type a size in GB, such as 20.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });
});

describe("the Settings sections", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("fold under their headings, and stay folded on the next visit", async () => {
    open(true);
    const heading = screen.getByRole("button", { name: "Keyboard shortcuts" });

    await userEvent.click(heading);

    expect(heading).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Reset to defaults" })).not.toBeInTheDocument();

    cleanup();
    open(true);

    expect(screen.getByRole("button", { name: "Keyboard shortcuts" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("open from their names at the top, which go to them", async () => {
    localStorage.setItem("medleyplay.settings.folded.v1", JSON.stringify(["storage"]));
    open(true);
    const sections = screen.getByRole("navigation", { name: "Settings sections" });

    await userEvent.click(
      within(sections).getByRole("button", { name: "Go to Downloads and storage" }),
    );

    const heading = screen.getByRole("button", { name: "Downloads and storage" });
    expect(heading).toHaveAttribute("aria-expanded", "true");
    expect(heading).toHaveFocus();
    expect(await screen.findByText(/of 20 GB used/)).toBeVisible();
  });

  it("fold all at once, and open all again", async () => {
    open(true);

    await userEvent.click(screen.getByRole("button", { name: "Fold all" }));

    expect(
      screen.getAllByRole("button", { expanded: false }).map((button) => button.textContent),
    ).toEqual(["Appearance", "Keyboard shortcuts", "Network", "Downloads and storage"]);

    await userEvent.click(screen.getByRole("button", { name: "Open all" }));

    expect(screen.queryAllByRole("button", { expanded: false })).toEqual([]);
  });
});

describe("the Network section", () => {
  it("says why medleyplay is Offline, and the network the server is on", async () => {
    open(false, {}, ON_THE_HOTSPOT, [HOTSPOT_MARK]);

    expect(await network().findByText("Offline: on a metered network.")).toBeVisible();
    expect(network().getByText("On Wi-Fi, marked metered as “iPhone hotspot”.")).toBeVisible();
  });

  it("says when a settling Mode goes Online, and how many downloads wait", async () => {
    const settling = modeOf({
      online: false,
      reason: "settling",
      online_at: "2026-10-27T12:00:30Z",
      held_jobs: 2,
    });

    open(false, {}, settling);

    expect(await network().findByText(/Goes Online at .+ if nothing changes\./)).toBeVisible();
    expect(network().getByText("2 downloads wait for Online.")).toBeVisible();
  });

  it("lets an admin choose the setting, saved at the revision read", async () => {
    const served = open(true);

    await userEvent.click(await network().findByRole("radio", { name: /^Always Offline/ }));

    expect(network().getByRole("radio", { name: /^Always Offline/ })).toBeChecked();
    expect(served.calls).toContain("PUT /api/mode/settings");
  });

  it("shows the setting as it is now when it changed elsewhere", async () => {
    open(true, {
      "PUT /api/mode/settings": { status: 409, body: { detail: "Saved since." } },
    });

    await userEvent.click(await network().findByRole("radio", { name: /^Always Online/ }));

    expect(await network().findByText(/changed elsewhere/)).toBeVisible();
    expect(network().getByRole("radio", { name: /^Auto/ })).toBeChecked();
  });

  it("lets an admin mark the network the server is on metered, and remove the mark", async () => {
    open(true);

    await userEvent.type(
      await network().findByRole("textbox", { name: /Mark this network/ }),
      "Office",
    );
    await userEvent.click(network().getByRole("button", { name: "Mark metered" }));
    const removing = await network().findByRole("button", { name: "Remove the mark on Office" });
    await userEvent.click(removing);

    await waitFor(() => {
      expect(network().queryByText("Office")).not.toBeInTheDocument();
    });
  });

  it("says a network on a phone hotspot's usual subnet looks like one", async () => {
    const onAHotspot = modeOf({
      network: { kind: "wifi", metered_as: null, hotspot_like: true },
    });

    open(true, {}, onAHotspot);

    expect(await network().findByText("This network looks like a phone's hotspot.")).toBeVisible();
  });

  it("shows a member the setting and the marks, with nothing to change", async () => {
    open(false, {}, ON_THE_HOTSPOT, [HOTSPOT_MARK]);

    expect(await network().findByText(/^Auto: .+\. An admin changes this\.$/)).toBeVisible();
    expect(network().getByText("iPhone hotspot")).toBeVisible();
    expect(network().queryByRole("radio")).not.toBeInTheDocument();
    expect(network().queryByRole("button", { name: /Remove/ })).not.toBeInTheDocument();
  });
});
