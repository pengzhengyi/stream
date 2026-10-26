import { type Page, expect as baseExpect, test } from "@playwright/test";

// Playback runs on the audio clock, which a busy machine slows; waits allow for that.
const expect = baseExpect.configure({ timeout: 15_000 });

const player = (page: Page) => page.getByRole("region", { name: "Player" });
const paused = (page: Page) =>
  page.locator("audio").evaluate((audio: HTMLAudioElement) => audio.paused);

/** Play `title` by clicking it, which leaves its button focused, as a mouse does. */
async function play(page: Page, title: string) {
  await page.goto("/");
  await page.getByRole("button", { name: title, exact: true }).click();
  await expect(player(page).getByRole("button", { name: "Pause" })).toBeVisible();
}

test("Space pauses the song just clicked, and plays it again", async ({ page }) => {
  await play(page, "Alpha");

  await page.keyboard.press("Space");

  await expect(player(page).getByRole("button", { name: "Play" })).toBeVisible();
  await expect.poll(() => paused(page)).toBe(true);

  await page.keyboard.press("Space");

  await expect.poll(() => paused(page)).toBe(false);
  await expect(player(page).getByText("Alpha", { exact: true })).toBeVisible();
});

test("Shift and → skips to the next song", async ({ page }) => {
  await play(page, "Alpha");

  await page.keyboard.press("Shift+ArrowRight");

  await expect(player(page).getByText("Bravo", { exact: true })).toBeVisible();
});

test("/ goes to the search box, where the keys type", async ({ page }) => {
  await play(page, "Alpha");

  await page.keyboard.press("Slash");
  await page.keyboard.type("s ");

  await expect(page.getByRole("searchbox")).toHaveValue("s ");
  await expect(player(page).getByRole("button", { name: "Pause" })).toBeVisible();
});

test("? lists the shortcuts, and Escape puts the list away", async ({ page }) => {
  await page.goto("/");
  const list = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(page.getByRole("button", { name: "Alpha", exact: true })).toBeVisible();

  await page.keyboard.press("Shift+Slash");

  await expect(list.getByText("Play or pause")).toBeVisible();
  await expect(list.getByRole("link", { name: "Change them in Settings" })).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(list).toBeHidden();
});

test("a control names its keys on hover", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: "Keyboard shortcuts" })).toHaveAttribute(
    "title",
    "Keyboard shortcuts (Shift + /)",
  );
});

test("keys added in Settings work from then on, in any browser the Account signs in to", async ({
  page,
  browser,
}) => {
  await page.goto("/#/settings");
  const section = page.getByRole("region", { name: "Keyboard shortcuts" });
  const status = section.getByRole("status");

  // Other tests share the Account, so this adds a key rather than moving one, and resets.
  await page.getByRole("button", { name: "Add keys to Play or pause" }).click();
  await page.keyboard.press("KeyS");
  await expect(status).toHaveText("S is already Shuffle. Press other keys.");
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/me/preferences") && response.request().method() === "PUT",
  );
  await page.keyboard.press("KeyJ");
  await expect(status).toHaveText("Play or pause now also has J.");
  expect((await saved).ok()).toBe(true);

  // Another device: the same sign-in, but nothing this browser kept.
  const { cookies } = await page.context().storageState();
  const elsewhere = await browser.newContext({ storageState: { cookies, origins: [] } });
  try {
    const other = await elsewhere.newPage();
    await play(other, "Alpha");
    await other.keyboard.press("KeyJ");

    await expect.poll(() => paused(other)).toBe(true);
  } finally {
    await elsewhere.close();
    await section.getByRole("button", { name: "Reset to defaults" }).click();
    await expect(status).toHaveText("Back to the usual keys.");
  }
});

test("Space taken in Settings keeps waiting for other keys", async ({ page }) => {
  await page.goto("/#/settings");
  const status = page.getByRole("region", { name: "Keyboard shortcuts" }).getByRole("status");

  await page.getByRole("button", { name: "Add keys to Shuffle" }).click();
  await page.keyboard.press("Space");

  await expect(status).toHaveText("Space is already Play or pause. Press other keys.");
  await expect(page.getByRole("button", { name: "Press keys to add to Shuffle" })).toBeFocused();
});

test("K plays or pauses too, and M mutes", async ({ page }) => {
  await play(page, "Alpha");

  await page.keyboard.press("KeyK");
  await expect.poll(() => paused(page)).toBe(true);
  await page.keyboard.press("KeyM");

  await expect(page.locator("audio")).toHaveJSProperty("muted", true);
  await expect(page.getByRole("slider", { name: "Volume" })).toHaveAttribute(
    "aria-valuetext",
    /^Muted/,
  );
});
