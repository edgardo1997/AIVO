import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppProvider } from "../contexts/AppContext";
import { Plugins } from "../components/Plugins/Plugins";

const mockApi = vi.hoisted(() => ({
  plugins: {
    list: vi.fn().mockResolvedValue({ plugins: [
      { id: "p1", name: "Plugin One", version: "1.0.0", description: "First plugin", author: "Author1", has_code: true, enabled: true, loaded: true, is_builtin: false },
      { id: "p2", name: "Plugin Two", version: "2.0.0", description: "Second plugin", author: "Author2", has_code: false, enabled: false, loaded: false, is_builtin: true },
    ] }),
    templates: vi.fn().mockResolvedValue({ templates: ["minimal", "full"] }),
    load: vi.fn().mockResolvedValue({ status: "loaded" }),
    unload: vi.fn().mockResolvedValue({ status: "unloaded" }),
    reload: vi.fn().mockResolvedValue({ status: "reloaded" }),
    toggle: vi.fn().mockResolvedValue({ status: "toggled", enabled: true }),
    create: vi.fn().mockResolvedValue({ status: "created" }),
    marketplace: vi.fn().mockResolvedValue({ plugins: [] }),
    installFromUrl: vi.fn(),
    exportPlugin: vi.fn(),
    verify: vi.fn(),
  },
  permissions: { status: vi.fn().mockResolvedValue({ level: "auto", emergency_stop: false, pending_actions: 0 }), rules: vi.fn().mockResolvedValue({ rules: [] }), setLevel: vi.fn(), emergency: vi.fn(), addRule: vi.fn(), deleteRule: vi.fn() },
  monitor: { system: vi.fn().mockResolvedValue({}) },
}));

vi.mock("../api", () => ({ api: mockApi }));

describe("Plugins", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows plugin list", async () => {
    render(<AppProvider><Plugins /></AppProvider>);
    expect(await screen.findByText("Plugin One")).toBeInTheDocument();
    expect(screen.getByText("Plugin Two")).toBeInTheDocument();
  });

  it("shows Create New Plugin section", async () => {
    render(<AppProvider><Plugins /></AppProvider>);
    await screen.findByText("Plugin One");
    expect(screen.getByPlaceholderText(/Plugin name/)).toBeInTheDocument();
    expect(screen.getByText("Create")).toBeInTheDocument();
  });

  it("activates toggle on click", async () => {
    render(<AppProvider><Plugins /></AppProvider>);
    await screen.findByText("Plugin One");
    const toggleBtn = screen.getByText("Disable");
    fireEvent.click(toggleBtn);
    await waitFor(() => {
      expect(mockApi.plugins.toggle).toHaveBeenCalledWith("p1");
    });
  });
});
