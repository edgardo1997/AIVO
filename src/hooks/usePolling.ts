import { useEffect, useRef } from "react";

/**
 * Runs `callback` once on mount and then repeatedly every `intervalMs`,
 * clearing the interval on unmount. Errors thrown by the callback are ignored
 * so a single failed poll does not tear down the interval.
 */
export function usePolling(callback: () => void | Promise<void>, intervalMs: number) {
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    const tick = () => {
      try {
        void Promise.resolve(savedCallback.current()).catch(() => {});
      } catch {
        /* ignore */
      }
    };
    tick();
    const interval = setInterval(tick, intervalMs);
    return () => clearInterval(interval);
  }, [intervalMs]);
}
