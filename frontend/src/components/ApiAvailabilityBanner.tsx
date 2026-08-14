"use client";

import {
  CloudOff,
  LoaderCircle,
  RefreshCw,
  TriangleAlert,
  WifiOff,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  checkApiAvailability,
  type ApiAvailability,
} from "@/lib/api-availability";

const RETRY_DELAY_MS: Record<Exclude<ApiAvailability, "live">, number> = {
  warming: 10_000,
  offline: 30_000,
  "device-offline": 30_000,
  error: 30_000,
};

const PROBE_TIMEOUT_MS = 8_000;

const COPY: Record<
  Exclude<ApiAvailability, "live">,
  { title: string; description: string }
> = {
  warming: {
    title: "Demo is warming up",
    description:
      "The learning API is starting and checking its database. It should be ready in a few minutes.",
  },
  offline: {
    title: "Demo API is offline",
    description:
      "It may be asleep between demo sessions. You can still explore the site and try again after it is started.",
  },
  "device-offline": {
    title: "You’re offline",
    description:
      "Reconnect this device to the internet. This is different from the demo API being asleep.",
  },
  error: {
    title: "Demo API needs attention",
    description:
      "The API responded with an unexpected health status. This is not classified as a sleeping environment.",
  },
};

function StatusIcon({ status }: { status: Exclude<ApiAvailability, "live"> }) {
  const props = { "aria-hidden": true, size: 20, strokeWidth: 2 } as const;
  if (status === "warming") return <LoaderCircle {...props} className="animate-spin" />;
  if (status === "offline") return <CloudOff {...props} />;
  if (status === "device-offline") return <WifiOff {...props} />;
  return <TriangleAlert {...props} />;
}

interface ApiAvailabilityBannerProps {
  checkAvailability?: typeof checkApiAvailability;
}

export function ApiAvailabilityBanner({
  checkAvailability = checkApiAvailability,
}: ApiAvailabilityBannerProps = {}) {
  const [status, setStatus] = useState<ApiAvailability | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const requestId = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeController = useRef<AbortController | null>(null);

  const probe = useCallback(async () => {
    const currentRequest = ++requestId.current;
    if (retryTimer.current) clearTimeout(retryTimer.current);
    activeController.current?.abort();
    setIsChecking(true);

    const controller = new AbortController();
    activeController.current = controller;
    const timeout = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);

    try {
      const nextStatus = await checkAvailability({ signal: controller.signal });
      if (currentRequest !== requestId.current) return;

      setStatus(nextStatus);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) throw error;
      if (currentRequest !== requestId.current) return;
      setStatus(navigator.onLine ? "offline" : "device-offline");
    } finally {
      clearTimeout(timeout);
      if (currentRequest === requestId.current) {
        activeController.current = null;
        setIsChecking(false);
      }
    }
  }, [checkAvailability]);

  useEffect(() => {
    if (!status || status === "live") return;
    retryTimer.current = setTimeout(() => {
      if (document.visibilityState === "visible") void probe();
    }, RETRY_DELAY_MS[status]);
    return () => {
      if (retryTimer.current) clearTimeout(retryTimer.current);
    };
  }, [probe, status]);

  useEffect(() => {
    const initialProbe = setTimeout(() => void probe(), 0);

    const checkWhenVisible = () => {
      if (document.visibilityState === "visible") void probe();
    };
    const checkWhenOnline = () => void probe();

    document.addEventListener("visibilitychange", checkWhenVisible);
    window.addEventListener("online", checkWhenOnline);

    return () => {
      clearTimeout(initialProbe);
      requestId.current += 1;
      activeController.current?.abort();
      if (retryTimer.current) clearTimeout(retryTimer.current);
      document.removeEventListener("visibilitychange", checkWhenVisible);
      window.removeEventListener("online", checkWhenOnline);
    };
  }, [probe]);

  if (!status || status === "live") return null;

  const copy = COPY[status];

  return (
    <aside
      aria-live="polite"
      className="api-availability-banner"
      data-api-availability={status}
      role="status"
    >
      <span className="api-availability-icon">
        <StatusIcon status={status} />
      </span>
      <span className="api-availability-copy">
        <strong>{copy.title}</strong>
        <span>{copy.description}</span>
      </span>
      <button type="button" onClick={() => void probe()} disabled={isChecking}>
        <RefreshCw
          aria-hidden="true"
          className={isChecking ? "animate-spin" : undefined}
          size={16}
        />
        {isChecking ? "Checking…" : "Try again"}
      </button>
    </aside>
  );
}
