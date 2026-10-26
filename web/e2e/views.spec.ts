// cspell:ignore charl
import { type Page, expect, test } from "@playwright/test";

const nav = (page: Page) => page.getByRole("navigation", { name: "Views" });

test("the views follow the links, Back, and Forward", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Alpha", exact: true })).toBeVisible();

  await nav(page).getByRole("link", { name: "Artists" }).click();
  // The test music has no tags, so its songs are by no one in particular.
  await page.getByRole("link", { name: /Unknown artist/ }).click();
  await expect(page.getByRole("heading", { name: "Unknown artist" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Delta", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Artists" })).toBeVisible();
  await page.goForward();

  await expect(page.getByRole("heading", { name: "Unknown artist" })).toBeVisible();
  await expect(nav(page).getByRole("link", { name: "Artists" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("a view's link opens it again after a reload", async ({ page }) => {
  await page.goto("/#/playlists");
  await page
    .getByRole("link", { name: /Favorites/ })
    .first()
    .click();

  await page.reload();

  await expect(page.getByRole("heading", { name: "Favorites" })).toBeVisible();
});

test("searching finds songs as you type, and Back leaves the search in one step", async ({
  page,
}) => {
  await page.goto("/#/albums");

  await page.getByRole("searchbox", { name: "Search" }).fill("charl");

  const found = page.getByRole("region", { name: "Songs found" });
  await expect(found.getByRole("button", { name: "Charlie", exact: true })).toBeVisible();
  await page.getByRole("searchbox", { name: "Search" }).fill("charlie");
  await expect(page.getByRole("heading", { name: "Results for “charlie”" })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Albums" })).toBeVisible();
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the views are a tab bar, and the queue opens from the player", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Alpha", exact: true }).click();
    const queue = page.getByRole("region", { name: "Up next" });
    await expect(queue).toBeHidden();

    await page.getByRole("button", { name: "Up next" }).click();

    await expect(queue.getByRole("listitem")).toHaveText([/Bravo/, /Charlie/, /Delta/]);
    await expect(page.getByRole("button", { name: "Up next" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    await nav(page).getByRole("link", { name: "Albums" }).click();
    await expect(page.getByRole("heading", { name: "Albums" })).toBeVisible();
  });
});
