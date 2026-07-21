import { afterEach, describe, expect, it, vi } from "vitest";

describe("local Tauri session recovery", () => {
  afterEach(() => {
    vi.doUnmock("@tauri-apps/api/core");
    vi.resetModules();
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  it("requests a fresh session token after a transient native failure", async () => {
    const invoke = vi.fn()
      .mockRejectedValueOnce(new Error("sidecar starting"))
      .mockResolvedValueOnce("fresh-local-session");
    Object.defineProperty(window, "__TAURI_INTERNALS__", {
      configurable: true,
      value: {},
    });
    vi.doMock("@tauri-apps/api/core", () => ({
      Channel: class TestChannel {},
      invoke,
    }));
    const { auth } = await import("../api");

    await auth.connectLocal().catch(() => {});
    const result = await auth.connectLocal();
    expect(result).toEqual({ authentication_method: "local_session" });
    auth.logout();
  });
});
