import { useEffect, useRef } from "react";

export function usePolling(
  callback: (signal: AbortSignal) => void | Promise<void>,
  intervalMs: number,
  enabled = true,
) {
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    const abort = new AbortController();

    const scheduleNext = () => {
      if (active) timeoutId = setTimeout(tick, intervalMs);
    };

    const tick = () => {
      if (!active) return;
      try {
        const result = savedCallback.current(abort.signal);
        if (result instanceof Promise) {
          result.then(scheduleNext).catch(scheduleNext);
        } else {
          scheduleNext();
        }
      } catch {
        scheduleNext();
      }
    };

    tick();

    return () => {
      active = false;
      abort.abort();
      if (timeoutId !== null) clearTimeout(timeoutId);
    };
  }, [intervalMs, enabled]);
}
