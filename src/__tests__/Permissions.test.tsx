import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Permissions } from "../components/Permissions/Permissions";
import { AppProvider } from "../contexts/AppContext";

vi.mock("../api", () => ({
  api: {
    permissions: {
      status: vi.fn().mockResolvedValue({ level: "auto", emergency_stop: false, pending_actions: 0 }),
      rules: vi.fn().mockResolvedValue({ rules: [] }),
      setLevel: vi.fn().mockResolvedValue({}),
      emergency: vi.fn().mockResolvedValue({}),
      addRule: vi.fn().mockResolvedValue({}),
      deleteRule: vi.fn().mockResolvedValue({}),
    },
    monitor: { system: vi.fn().mockResolvedValue({}) },
  },
}));

describe("Permissions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra permission levels", async () => {
    render(<AppProvider><Permissions /></AppProvider>);
    expect(await screen.findByText("View Only")).toBeInTheDocument();
    expect(screen.getByText("Confirm")).toBeInTheDocument();
    expect(screen.getByText("Auto")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
  });

  it("muestra Emergency Stop button", async () => {
    render(<AppProvider><Permissions /></AppProvider>);
    expect(await screen.findByText("Emergency Stop")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Emergency Stop"));
    expect(await screen.findByText("Confirm Action")).toBeInTheDocument();
    expect(screen.getByText(/ACTIVATING EMERGENCY STOP/)).toBeInTheDocument();
  });
});
