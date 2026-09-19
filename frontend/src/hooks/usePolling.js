import { useEffect, useRef } from "react";

/**
 * Phase 2, Feature 8 — "real-time feel" without any real-time infrastructure.
 *
 * Calls `callback` every `intervalMs` milliseconds while the tab is visible.
 * No websockets, no Redis, no push service — just setInterval hitting the
 * existing REST endpoints, which is plenty for a demo and impossible to break.
 *
 * Pausing when the tab is hidden keeps the backend quiet when nobody is looking.
 */
export default function usePolling(callback, intervalMs = 10000, enabled = true) {
  const savedCallback = useRef(callback);

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled || !intervalMs) return undefined;

    const tick = () => {
      if (document.visibilityState === "visible") {
        savedCallback.current?.();
      }
    };

    const id = setInterval(tick, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, enabled]);
}
