import { type Page, expect, test } from "@playwright/test";

const row = (page: Page, title: string) =>
  page.getByRole("row").filter({ has: page.getByRole("button", { name: title, exact: true }) });

test("a favorite and a rating are kept by the server", async ({ page }) => {
  await page.goto("/");
  const heart = page.getByRole("button", { name: "Favorite Bravo" }).first();
  const stars = row(page, "Bravo").getByRole("group", { name: "Rate Bravo" });

  await heart.click();
  await stars.getByRole("button", { name: "4 stars" }).click();
  await expect(heart).toHaveAttribute("aria-pressed", "true");
  await page.reload();

  await expect(page.getByRole("button", { name: "Favorite Bravo" }).first()).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(row(page, "Bravo").getByRole("button", { name: "4 stars" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  // Put Bravo back as the other tests expect it.
  await page.getByRole("button", { name: "Favorite Bravo" }).first().click();
  await row(page, "Bravo").getByRole("button", { name: "4 stars" }).click();
  await expect(row(page, "Bravo").getByRole("button", { name: "4 stars" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("sorting by time plays from the sorted order", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Time", exact: true }).click();
  await expect(page.getByRole("columnheader", { name: "Time" })).toHaveAttribute(
    "aria-sort",
    "ascending",
  );
  await page.getByRole("button", { name: "Charlie", exact: true }).click();

  const queue = page.getByRole("region", { name: "Up next" }).getByRole("listitem");
  await expect(queue).toHaveText([/Alpha/, /Bravo/, /Delta/]);
});

test("a large Library keeps only the rows on screen in the page", async ({ page }) => {
  const tracks = Array.from({ length: 5000 }, (_, i) => ({
    id: i + 1,
    title: `Song ${String(i + 1)}`,
    artist: `Artist ${String(i % 40)}`,
    album: `Album ${String(i % 90)}`,
    album_artist: "",
    duration_ms: 180_000,
    added_at: "2026-10-01T12:00:00Z",
    favorite: false,
    rating: null,
    play_count: 0,
    last_played_at: null,
    availability: "ok",
    downloaded: false,
  }));
  await page.route("**/api/tracks", (route) => route.fulfill({ json: tracks }));
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Song 1", exact: true })).toBeVisible();

  expect(await page.locator("table.tracks tbody tr:not(.spacer)").count()).toBeLessThan(100);
  await expect(page.getByRole("table")).toHaveAttribute("aria-rowcount", "5001");
  await page.mouse.wheel(0, 1_000_000);
  await expect(page.getByRole("button", { name: "Song 5000", exact: true })).toBeVisible();
  expect(await page.locator("table.tracks tbody tr:not(.spacer)").count()).toBeLessThan(100);
});
