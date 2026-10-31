import { describe, expect, it } from "vitest";

import { ApiError, api } from "./api";
import { serve } from "./testing/server";

describe("a refused request", () => {
  it("says each check the request failed, as the server lists them", async () => {
    serve({
      "PUT /api/tracks/104/songs": {
        status: 422,
        body: {
          detail: [
            { loc: ["body", "rows"], msg: "List should have at most 300 items after validation" },
            { loc: ["body", "known"], msg: "Input should be a valid integer" },
          ],
        },
      },
    });

    const refused = api.saveSongs(104, [], []);

    await expect(refused).rejects.toThrow(ApiError);
    await expect(refused).rejects.toThrow(
      "List should have at most 300 items after validation; Input should be a valid integer",
    );
  });

  it("says that it was refused when the server gave no reason", async () => {
    serve({ "DELETE /api/tracks/104/songs": { status: 500, body: "Internal Server Error" } });

    await expect(api.unsplit(104)).rejects.toThrow("The server refused this (500).");
  });
});
