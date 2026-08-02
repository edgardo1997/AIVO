import tauriConfigRaw from "../../src-tauri/tauri.conf.json?raw";
import { describe, expect, it } from "vitest";

describe("Tauri local-sidecar CSP", () => {
  it("allows the authenticated local event stream used by the interface", () => {
    const config = JSON.parse(tauriConfigRaw);
    const csp: string = config.app.security.csp;

    expect(csp).toContain("http://127.0.0.1:8765");
    expect(csp).toContain("ws://127.0.0.1:8765");
  });
});
