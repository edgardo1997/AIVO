import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "../hooks/usePolling";

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("llama al callback inmediatamente al montar", () => {
    const fn = vi.fn();
    renderHook(() => usePolling(fn, 5000));
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("llama al callback en el intervalo", () => {
    const fn = vi.fn();
    renderHook(() => usePolling(fn, 5000));

    vi.advanceTimersByTime(5000);
    expect(fn).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(10000);
    expect(fn).toHaveBeenCalledTimes(4);
  });

  it("no llama cuando enabled=false", () => {
    const fn = vi.fn();
    renderHook(() => usePolling(fn, 5000, false));
    expect(fn).not.toHaveBeenCalled();
  });

  it("usa la versión más reciente del callback", () => {
    const fn1 = vi.fn();
    const fn2 = vi.fn();
    const { rerender } = renderHook(({ cb }) => usePolling(cb, 5000), {
      initialProps: { cb: fn1 },
    });

    vi.advanceTimersByTime(5000);
    expect(fn1).toHaveBeenCalledTimes(2);

    rerender({ cb: fn2 });
    vi.advanceTimersByTime(5000);
    expect(fn2).toHaveBeenCalledTimes(1);
  });

  it("limpia el intervalo al desmontar", () => {
    const fn = vi.fn();
    const { unmount } = renderHook(() => usePolling(fn, 5000));
    expect(fn).toHaveBeenCalledTimes(1);

    unmount();
    vi.advanceTimersByTime(5000);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
