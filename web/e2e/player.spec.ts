import { type Page, expect as baseExpect, test } from "@playwright/test";

// Playback runs on the audio clock, which a busy machine slows; waits allow for that.
const expect = baseExpect.configure({ timeout: 15_000 });

/** The audio element's position and whether it is playing. */
async function audioState(page: Page) {
  return page.locator("audio").evaluate((audio: HTMLAudioElement) => ({
    playing: !audio.paused,
    position: audio.currentTime,
  }));
}

const player = (page: Page) => page.getByRole("region", { name: "Player" });
const upNext = (page: Page) => page.getByRole("region", { name: "Up next" }).getByRole("listitem");

async function play(page: Page, title: string) {
  await page.goto("/");
  await page.getByRole("button", { name: title, exact: true }).click();
  await expect(player(page).getByText(title, { exact: true })).toBeVisible();
}

test("choosing a Track plays it and queues the Tracks after it", async ({ page }) => {
  await play(page, "Alpha");

  await expect.poll(async () => (await audioState(page)).position).toBeGreaterThan(0.5);
  expect((await audioState(page)).playing).toBe(true);
  await expect(upNext(page)).toHaveText([/Bravo/, /Charlie/, /Delta/]);
  await expect(player(page).getByRole("button", { name: "Pause" })).toBeVisible();
});

test("the seek bar moves the playing position", async ({ page }) => {
  await play(page, "Alpha");
  await expect(player(page).getByRole("button", { name: "Pause" })).toBeVisible();

  await player(page).getByLabel("Position").fill("40");

  await expect.poll(async () => (await audioState(page)).position).toBeGreaterThanOrEqual(40);
});

test("pausing stops the audio, and playing goes on", async ({ page }) => {
  await play(page, "Alpha");

  await player(page).getByRole("button", { name: "Pause" }).click();
  await expect.poll(async () => (await audioState(page)).playing).toBe(false);
  await player(page).getByRole("button", { name: "Play" }).click();

  await expect.poll(async () => (await audioState(page)).playing).toBe(true);
});

test("a Track that ends moves on to the next", async ({ page }) => {
  await play(page, "Charlie");

  await expect(player(page).getByText("Delta", { exact: true })).toBeVisible();
});

test("a compressed Track is prepared, then plays", async ({ page }) => {
  await play(page, "Delta");

  await expect.poll(async () => (await audioState(page)).playing, { timeout: 30_000 }).toBe(true);
});

test("Next and Previous move through the queue", async ({ page }) => {
  await play(page, "Alpha");

  await player(page).getByRole("button", { name: "Next" }).click();
  await expect(player(page).getByText("Bravo", { exact: true })).toBeVisible();
  await player(page).getByRole("button", { name: "Previous" }).click();

  await expect(player(page).getByText("Alpha", { exact: true })).toBeVisible();
});

test("a reload keeps the queue, paused where it was", async ({ page }) => {
  await play(page, "Alpha");
  await player(page).getByLabel("Position").fill("20");
  await expect.poll(async () => (await audioState(page)).position).toBeGreaterThanOrEqual(21);

  await page.reload();

  await expect(player(page).getByText("Alpha", { exact: true })).toBeVisible();
  await expect(player(page).getByRole("button", { name: "Play" })).toBeEnabled();
  await expect.poll(async () => (await audioState(page)).position).toBeGreaterThanOrEqual(20);
  expect((await audioState(page)).playing).toBe(false);
  await expect(upNext(page)).toHaveText([/Bravo/, /Charlie/, /Delta/]);
});

test("dragging a Track by its handle puts it in another place in the queue", async ({ page }) => {
  await play(page, "Alpha");
  await expect(upNext(page)).toHaveText([/Bravo/, /Charlie/, /Delta/]);
  const queue = page.getByRole("region", { name: "Up next" });

  await queue
    .getByRole("button", { name: "Reorder Delta" })
    .dragTo(queue.getByRole("button", { name: "Reorder Bravo" }), { steps: 12 });

  await expect(upNext(page)).toHaveText([/Delta/, /Bravo/, /Charlie/]);
});

test("the keyboard moves a Track in the queue as dragging does", async ({ page }) => {
  await play(page, "Alpha");
  await expect(upNext(page)).toHaveText([/Bravo/, /Charlie/, /Delta/]);

  // Each step waits for what a screen reader hears, as a listener would.
  await page.getByRole("button", { name: "Reorder Bravo" }).focus();
  await page.keyboard.press("Space");
  await expect(page.getByText("Picked up Bravo.")).toBeAttached();
  // The sensor starts hearing keys a timeout after the pickup; this one runs after it.
  await page.evaluate(() => new Promise((resolve) => setTimeout(resolve, 0)));
  await page.keyboard.press("ArrowDown");
  await expect(page.getByText("Bravo would play second.")).toBeAttached();
  await page.keyboard.press("Space");

  await expect(upNext(page)).toHaveText([/Charlie/, /Bravo/, /Delta/]);
});

test("a theme chosen holds over the system's, and across a reload", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const html = page.locator("html");

  await page.getByRole("radio", { name: "Dark" }).click();
  await page.reload();

  await expect(html).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("radio", { name: "Match the system" }).click();
  await expect(html).not.toHaveAttribute("data-theme");
});
