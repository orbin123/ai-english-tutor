import { API_BASE_URL } from "@/lib/api-config";

export type ApiAvailability =
  | "live"
  | "warming"
  | "offline"
  | "device-offline"
  | "error";

interface CheckApiAvailabilityOptions {
  fetcher?: typeof fetch;
  online?: boolean;
  signal?: AbortSignal;
}

const WARMING_STATUS = 503;

export const API_READINESS_URL = `${API_BASE_URL.replace(/\/$/, "")}/health/ready`;

/**
 * Classify only the dedicated readiness probe. Feature request failures must
 * keep their own error handling and must never implicitly mark the API asleep.
 */
export async function checkApiAvailability({
  fetcher = fetch,
  online = typeof navigator === "undefined" ? true : navigator.onLine,
  signal,
}: CheckApiAvailabilityOptions = {}): Promise<ApiAvailability> {
  if (!online) return "device-offline";

  try {
    const response = await fetcher(API_READINESS_URL, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
      headers: { Accept: "application/json" },
      signal,
    });

    if (response.ok) return "live";
    if (response.status === WARMING_STATUS) return "warming";
    return "error";
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    return online ? "offline" : "device-offline";
  }
}
