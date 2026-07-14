import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Plugins } from "../components/Plugins/Plugins";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
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
    },
  },
}));

describe("Plugins", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra lista de plugins", async () => {
    render(<Plugins />);
    expect(await screen.findByText("Plugin One")).toBeInTheDocument();
    expect(screen.getByText("Plugin Two")).toBeInTheDocument();
  });

  it("muestra Create New Plugin section", async () => {
    render(<Plugins />);
    await screen.findByText("Plugin One");
    expect(screen.getByPlaceholderText(/Plugin name/)).toBeInTheDocument();
    expect(screen.getByText("Create")).toBeInTheDocument();
  });

  it("activa toggle al hacer click", async () => {
    render(<Plugins />);
    await screen.findByText("Plugin One");

    const toggleBtn = screen.getByText("Disable");
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(api.plugins.toggle).toHaveBeenCalledWith("p1");
    });
  });
});
