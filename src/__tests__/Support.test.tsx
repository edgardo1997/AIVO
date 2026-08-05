import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import Support from "../components/Support/Support";

vi.mock("../api/core", () => ({
  requestJSON: vi.fn().mockResolvedValue({
    product: "Sentinel",
    version: "0.1.0-alpha.1",
    build_id: "internal-alpha-test",
    channel: "internal-alpha",
    overall: "ok",
    local_ai: "online",
    cloud: "offline",
    last_check: "now",
    recent_errors: [],
  }),
  postJSON: vi.fn(),
  BASE: "http://127.0.0.1:8765",
}));

describe("Support panel", () => {
  it("renders version and build id", async () => {
    render(<Support />);
    expect(await screen.findByText("0.1.0-alpha.1")).toBeInTheDocument();
    expect(await screen.findByText("internal-alpha-test")).toBeInTheDocument();
  });

  it("uses human labels for status", async () => {
    render(<Support />);
    expect(await screen.findByText(/Motor de Sentinel/)).toBeInTheDocument();
    expect(await screen.findByText(/Cloud:/)).toBeInTheDocument();
  });

  it("shows build and status by default", async () => {
    render(<Support />);
    expect(screen.queryByText(/Ver detalles/)).toBeInTheDocument();
    expect(screen.queryByText(/Build ID:/)).toBeInTheDocument();
  });
});
