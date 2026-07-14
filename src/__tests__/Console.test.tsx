import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { Console } from "../components/Console/Console";
import { AppProvider } from "../contexts/AppContext";

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

vi.mock("../api", () => ({
  v1Api: {
    execute: vi.fn().mockResolvedValue({ success: true, data: { stdout: "result output\n", returncode: 0 }, requires_confirmation: false, action_id: null, duration_ms: null, error: null, pipeline: null }),
  },
  api: {
    permissions: {
      status: vi.fn().mockResolvedValue({ level: "auto", emergency_stop: false, pending_actions: 0 }),
    },
    monitor: {
      system: vi.fn().mockResolvedValue({}),
    },
  },
}));

describe("Console", () => {
  it("renders console header", async () => {
    render(<AppProvider><Console /></AppProvider>);
    expect(await screen.findByText("Console")).toBeInTheDocument();
    expect(screen.getByText(/Permission level: auto/)).toBeInTheDocument();
  });

  it("quick command buttons render", async () => {
    render(<AppProvider><Console /></AppProvider>);
    expect(await screen.findByText("System Info")).toBeInTheDocument();
    expect(screen.getByText("Network")).toBeInTheDocument();
    expect(screen.getByText("Process List")).toBeInTheDocument();
    expect(screen.getByText("Disk Usage")).toBeInTheDocument();
  });

  it("execute command", async () => {
    render(<AppProvider><Console /></AppProvider>);
    const input = await screen.findByPlaceholderText("> type a command...");
    fireEvent.change(input, { target: { value: "echo hello" } });
    fireEvent.click(screen.getByText("Run"));
    await waitFor(() => {
      expect(screen.getByText("> echo hello")).toBeInTheDocument();
    });
  });
});
