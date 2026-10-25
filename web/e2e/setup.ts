/**
 * @file Prepares the server once: Alice as the admin, and two scanned Libraries.
 *
 * The music is made by `serve.py`; every other test starts signed in as Alice.
 */

import { expect, test as setup } from "@playwright/test";

import { ALICE, MUSIC, SIGNED_IN } from "./fixtures";

setup("sign in as Alice and scan the music", async ({ request }) => {
  const created = await request.post("/api/setup", { data: ALICE });
  expect(created.status()).toBe(201);
  for (const library of [
    { name: "Music", kind: "folder", path: `${MUSIC}/Music` },
    { name: "Old Mixes", kind: "zip", path: `${MUSIC}/Old Mixes.zip` },
  ]) {
    const registered = await request.post("/api/libraries", { data: library });
    expect(registered.status()).toBe(201);
  }

  await expect
    .poll(async () => {
      const jobs = (await (await request.get("/api/jobs")).json()) as { state: string }[];
      return jobs.map((job) => job.state);
    })
    .toEqual(["succeeded", "succeeded"]);
  await request.storageState({ path: SIGNED_IN });
});
