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

test("keys taken in Settings say whose they are, and new keys work from then on", async ({
  page,
}) => {
  await page.goto("/#/settings");
  const status = page.getByRole("region", { name: "Keyboard shortcuts" }).getByRole("status");

  await page.getByRole("button", { name: "Change keys for Play or pause" }).click();
  await page.keyboard.press("KeyS");
  await expect(status).toHaveText("S is already Shuffle. Press other keys.");
  await page.keyboard.press("KeyK");
  await expect(status).toHaveText("Play or pause is now K.");
  await expect(page.getByRole("button", { name: "Change keys for Play or pause" })).toBeVisible();

  await play(page, "Alpha");
  await page.keyboard.press("KeyK");

  await expect.poll(() => paused(page)).toBe(true);
});

test("Space taken in Settings keeps waiting for other keys", async ({ page }) => {
  await page.goto("/#/settings");
  const status = page.getByRole("region", { name: "Keyboard shortcuts" }).getByRole("status");

  await page.getByRole("button", { name: "Change keys for Shuffle" }).click();
  await page.keyboard.press("Space");

  await expect(status).toHaveText("Space is already Play or pause. Press other keys.");
  await expect(page.getByRole("button", { name: "Press new keys for Shuffle" })).toBeFocused();
});
