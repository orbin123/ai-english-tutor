import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import {
  API_READINESS_URL,
  checkApiAvailability,
} from "@/lib/api-availability";
import { server } from "../../setup/msw/server";

describe("checkApiAvailability", () => {
  it("classifies a successful readiness response as live", async () => {
    server.use(http.get(API_READINESS_URL, () => HttpResponse.json({ status: "ready" })));

    await expect(checkApiAvailability()).resolves.toBe("live");
  });

  it("classifies a not-ready proxy or API response as warming", async () => {
    server.use(
      http.get(API_READINESS_URL, () =>
        HttpResponse.json({ status: "starting" }, { status: 503 }),
      ),
    );

    await expect(checkApiAvailability()).resolves.toBe("warming");
  });

  it("classifies an unreachable API as offline", async () => {
    server.use(http.get(API_READINESS_URL, () => HttpResponse.error()));

    await expect(checkApiAvailability({ online: true })).resolves.toBe("offline");
  });

  it("distinguishes the browser being offline from the API sleeping", async () => {
    await expect(checkApiAvailability({ online: false })).resolves.toBe(
      "device-offline",
    );
  });

  it("does not misclassify an unexpected API error as sleep or warm-up", async () => {
    server.use(
      http.get(API_READINESS_URL, () =>
        HttpResponse.json({ detail: "internal error" }, { status: 500 }),
      ),
    );

    await expect(checkApiAvailability()).resolves.toBe("error");
  });

  it("does not label generic gateway failures as warm-up", async () => {
    server.use(
      http.get(API_READINESS_URL, () =>
        HttpResponse.json({ detail: "bad gateway" }, { status: 502 }),
      ),
    );

    await expect(checkApiAvailability()).resolves.toBe("error");
  });
});
