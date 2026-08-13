"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { MAX_AUDIO_RECORDING_SECONDS } from "@/lib/audio-limits";

export type VoiceRecorderState =
  | "idle"
  | "recording"
  | "paused"
  | "transcribing"
  | "error";

const MAX_DURATION_MS = MAX_AUDIO_RECORDING_SECONDS * 1_000;
const TICK_MS = 200;

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/ogg",
  "audio/mp4",
];

function pickMimeType(): string {
  if (typeof window === "undefined" || typeof MediaRecorder === "undefined") return "";
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t)) ?? "";
}

export function extensionForMime(mime: string): string {
  if (mime.includes("ogg")) return ".ogg";
  if (mime.includes("mp4")) return ".mp4";
  return ".webm";
}

export function isVoiceRecordingSupported(): boolean {
  if (typeof window === "undefined") return false;
  if (typeof MediaRecorder === "undefined") return false;
  if (!navigator.mediaDevices?.getUserMedia) return false;
  return pickMimeType() !== "";
}

interface UseVoiceRecorderReturn {
  state: VoiceRecorderState;
  elapsedMs: number;
  errorMessage: string | null;
  mimeType: string;
  start: () => Promise<void>;
  pause: () => void;
  resume: () => void;
  stop: () => Promise<Blob | null>;
  cancel: () => void;
  setTranscribing: (on: boolean) => void;
  setError: (message: string | null) => void;
  reset: () => void;
}

export function useVoiceRecorder(): UseVoiceRecorderReturn {
  const [state, setState] = useState<VoiceRecorderState>("idle");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState<string>("");

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Wall-clock based timer state
  const segmentStartRef = useRef<number>(0);
  const accumulatedMsRef = useRef<number>(0);
  const stopResolverRef = useRef<((blob: Blob | null) => void) | null>(null);
  const pendingAutoBlobRef = useRef<Blob | null>(null);

  const clearTimer = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const releaseStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  const reset = useCallback(() => {
    clearTimer();
    releaseStream();
    recorderRef.current = null;
    chunksRef.current = [];
    accumulatedMsRef.current = 0;
    segmentStartRef.current = 0;
    stopResolverRef.current = null;
    setElapsedMs(0);
    setErrorMessage(null);
    setState("idle");
  }, []);

  useEffect(() => {
    return () => {
      clearTimer();
      try {
        if (recorderRef.current && recorderRef.current.state !== "inactive") {
          recorderRef.current.stop();
        }
      } catch {
        /* ignore */
      }
      releaseStream();
    };
  }, []);

  const tick = () => {
    const now = Date.now();
    const total = accumulatedMsRef.current + (now - segmentStartRef.current);
    if (total >= MAX_DURATION_MS) {
      setElapsedMs(MAX_DURATION_MS);
      try {
        if (recorderRef.current && recorderRef.current.state !== "inactive") {
          recorderRef.current.stop();
        }
      } catch {
        /* ignore */
      }
    } else {
      setElapsedMs(total);
    }
  };

  const startTimer = () => {
    segmentStartRef.current = Date.now();
    clearTimer();
    timerRef.current = setInterval(tick, TICK_MS);
  };

  const freezeTimer = () => {
    clearTimer();
    accumulatedMsRef.current += Date.now() - segmentStartRef.current;
    if (accumulatedMsRef.current > MAX_DURATION_MS) {
      accumulatedMsRef.current = MAX_DURATION_MS;
    }
    setElapsedMs(accumulatedMsRef.current);
  };

  const start = useCallback(async () => {
    if (state !== "idle" && state !== "error") return;
    setErrorMessage(null);
    chunksRef.current = [];
    accumulatedMsRef.current = 0;
    setElapsedMs(0);

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      const name = (err as DOMException)?.name;
      let msg = "Couldn't access the microphone.";
      if (name === "NotAllowedError" || name === "SecurityError") {
        msg = "Microphone access blocked. Enable it in your browser settings.";
      } else if (name === "NotFoundError" || name === "OverconstrainedError") {
        msg = "No microphone detected.";
      } else if (name === "NotReadableError") {
        msg = "Microphone is busy. Close other apps using it and try again.";
      }
      setErrorMessage(msg);
      setState("error");
      return;
    }

    streamRef.current = stream;
    const mime = pickMimeType();
    setMimeType(mime);
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
    } catch {
      releaseStream();
      setErrorMessage("Recording isn't supported in this browser.");
      setState("error");
      return;
    }
    recorderRef.current = recorder;

    recorder.ondataavailable = (e: BlobEvent) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      clearTimer();
      releaseStream();
      const usedMime = recorder.mimeType || mime || "audio/webm";
      const blob = chunksRef.current.length
        ? new Blob(chunksRef.current, { type: usedMime })
        : null;
      const resolver = stopResolverRef.current;
      stopResolverRef.current = null;
      if (resolver) {
        resolver(blob);
      } else {
        // Auto-stop fired before caller invoked stop().
        // Stash the blob; the Composer reacts to `elapsedMs >= MAX` by calling
        // stop(), which picks up the pending blob synchronously.
        pendingAutoBlobRef.current = blob;
      }
    };

    try {
      recorder.start(250);
    } catch {
      releaseStream();
      setErrorMessage("Couldn't start the recorder.");
      setState("error");
      return;
    }
    startTimer();
    setState("recording");
  }, [state]);

  const pause = useCallback(() => {
    if (state !== "recording") return;
    const recorder = recorderRef.current;
    if (!recorder) return;
    try {
      if (recorder.state === "recording") recorder.pause();
    } catch {
      /* ignore */
    }
    freezeTimer();
    setState("paused");
  }, [state]);

  const resume = useCallback(() => {
    if (state !== "paused") return;
    if (accumulatedMsRef.current >= MAX_DURATION_MS) return;
    const recorder = recorderRef.current;
    if (!recorder) return;
    try {
      if (recorder.state === "paused") recorder.resume();
    } catch {
      /* ignore */
    }
    startTimer();
    setState("recording");
  }, [state]);

  const stop = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      // If auto-stop already produced a blob, return it immediately.
      if (pendingAutoBlobRef.current) {
        const blob = pendingAutoBlobRef.current;
        pendingAutoBlobRef.current = null;
        resolve(blob);
        return;
      }
      const recorder = recorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        resolve(null);
        return;
      }
      stopResolverRef.current = resolve;
      try {
        recorder.stop();
      } catch {
        stopResolverRef.current = null;
        resolve(null);
      }
    });
  }, []);

  const cancel = useCallback(() => {
    const recorder = recorderRef.current;
    stopResolverRef.current = null;
    pendingAutoBlobRef.current = null;
    chunksRef.current = [];
    try {
      if (recorder && recorder.state !== "inactive") recorder.stop();
    } catch {
      /* ignore */
    }
    clearTimer();
    releaseStream();
    accumulatedMsRef.current = 0;
    setElapsedMs(0);
    setState("idle");
  }, []);

  const setTranscribing = useCallback((on: boolean) => {
    setState(on ? "transcribing" : "idle");
    if (!on) {
      accumulatedMsRef.current = 0;
      setElapsedMs(0);
    }
  }, []);

  const setError = useCallback((message: string | null) => {
    setErrorMessage(message);
    setState(message ? "error" : "idle");
  }, []);

  return {
    state,
    elapsedMs,
    errorMessage,
    mimeType,
    start,
    pause,
    resume,
    stop,
    cancel,
    setTranscribing,
    setError,
    reset,
  };
}
