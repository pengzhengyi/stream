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

test("dragging the seek bar moves the audio only once let go", async ({ page }) => {
  await play(page, "Alpha");
  // The bar takes a drag once the Track's length is known.
  await expect(player(page).getByLabel("Position")).toBeEnabled();
  const bar = await player(page).getByLabel("Position").boundingBox();
  if (bar === null) {
    throw new Error("The seek bar isn't on the page.");
  }
  const y = bar.y + bar.height / 2;

  await page.mouse.move(bar.x + bar.width * 0.05, y);
  await page.mouse.down();
  await page.mouse.move(bar.x + bar.width * 0.6, y, { steps: 12 });

  await expect(player(page).getByText(/^0:3\d/)).toBeVisible();
  expect((await audioState(page)).position).toBeLessThan(10);
  await page.mouse.up();
  await expect.poll(async () => (await audioState(page)).position).toBeGreaterThanOrEqual(30);
  expect((await audioState(page)).playing).toBe(true);
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

test("choosing a Track queues the whole list, so Previous reaches the Tracks before it", async ({
  page,
}) => {
  await play(page, "Bravo");
  await player(page).getByRole("button", { name: "Pause" }).click();

  await player(page).getByRole("button", { name: "Previous" }).click();

  await expect(player(page).getByText("Alpha", { exact: true })).toBeVisible();
});

test("shuffle reorders what plays next, and turned off puts it back", async ({ page }) => {
  await play(page, "Alpha");
  const shuffle = player(page).getByRole("button", { name: "Shuffle" });

  await shuffle.click();

  await expect(shuffle).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("status").filter({ hasText: "Shuffle on." })).toBeAttached();
  const shuffled = await upNext(page).allTextContents();
  expect(shuffled.map((text) => /Bravo|Charlie|Delta/.exec(text)?.[0]).sort()).toEqual([
    "Bravo",
    "Charlie",
    "Delta",
  ]);
  await shuffle.click();
  await expect(upNext(page)).toHaveText([/Bravo/, /Charlie/, /Delta/]);
});

test("repeat one starts the Track over when it ends", async ({ page }) => {
  await page.goto("/");
  const repeat = player(page).getByRole("button", { name: /^Repeat/ });
  await repeat.click();
  await repeat.click();
  await expect(repeat).toHaveAccessibleName("Repeat: one");
  await page.locator("audio").evaluate((audio: HTMLAudioElement) => {
    audio.dataset.ends = "0";
    audio.addEventListener("ended", () => {
      audio.dataset.ends = String(Number(audio.dataset.ends) + 1);
    });
  });

  await page.getByRole("button", { name: "Charlie", exact: true }).click();

  await expect(page.locator("audio")).not.toHaveAttribute("data-ends", "0");
  await expect(player(page).getByText("Charlie", { exact: true })).toBeVisible();
  await expect.poll(async () => (await audioState(page)).playing).toBe(true);
});

test("repeat all plays the first Track after the last", async ({ page }) => {
  await page.goto("/");
  const repeat = player(page).getByRole("button", { name: /^Repeat/ });
  await repeat.click();
  await expect(repeat).toHaveAccessibleName("Repeat: all");
  await expect(page.getByRole("status").filter({ hasText: "Repeating the queue." })).toBeAttached();
  await page.getByRole("button", { name: "Delta", exact: true }).click();

  await player(page).getByRole("button", { name: "Next" }).click();

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

const volumeOf = (page: Page) =>
  page.locator("audio").evaluate((audio: HTMLAudioElement) => audio.volume);

test("the volume buttons step it one mark, and the volume stays after a reload", async ({
  page,
}) => {
  await play(page, "Alpha");

  await player(page).getByRole("button", { name: "Volume down" }).click();
  await player(page).getByRole("button", { name: "Volume down" }).click();
  await player(page).getByRole("button", { name: "Volume up" }).click();

  await expect.poll(() => volumeOf(page)).toBeCloseTo(0.9);
  await page.reload();
  await expect.poll(() => volumeOf(page)).toBeCloseTo(0.9);
  await expect(player(page).getByRole("slider", { name: "Volume" })).toHaveAttribute(
    "aria-valuetext",
    "90%",
  );
});

test("dragging the volume bar changes the volume only once let go", async ({ page }) => {
  await play(page, "Alpha");
  const bar = await player(page).getByRole("slider", { name: "Volume" }).boundingBox();
  if (bar === null) {
    throw new Error("The volume bar isn't on the page.");
  }
  const y = bar.y + bar.height / 2;

  await page.mouse.move(bar.x + bar.width - 2, y);
  await page.mouse.down();
  await page.mouse.move(bar.x + bar.width * 0.3, y, { steps: 8 });

  expect(await volumeOf(page)).toBe(1);
  await page.mouse.up();
  await expect.poll(() => volumeOf(page)).toBeLessThan(0.5);
});

test("Play all plays the view's songs in its order", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Play all" }).click();

  await expect(player(page).getByText("Alpha", { exact: true })).toBeVisible();
  await expect(upNext(page)).toHaveText([/Bravo/, /Charlie/, /Delta/]);
  await expect(player(page).getByRole("button", { name: "Shuffle" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("Shuffle all plays every song of the view, shuffled", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Shuffle all" }).click();

  await expect(player(page).getByRole("button", { name: "Shuffle" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(upNext(page)).toHaveCount(3);
  const playing = await player(page).locator(".names strong").textContent();
  const next = (await upNext(page).allTextContents()).map(
    (text) => /Alpha|Bravo|Charlie|Delta/.exec(text)?.[0],
  );
  expect([playing, ...next].sort()).toEqual(["Alpha", "Bravo", "Charlie", "Delta"]);
});
