import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Triggers } from "../components/Triggers/Triggers";

vi.mock("../api", () => ({
  api: {
    triggers: {
      list: vi.fn().mockResolvedValue({ triggers: [
        { id: "t1", name: "High CPU", description: "Triggers when CPU > 90%", conditions: [{ metric: "cpu_percent", operator: "gt", value: 90 }], action: { tool_id: "system.diagnostic", params: {} }, cooldown_seconds: 300, enabled: true, last_fired: null, created_at: "2024-01-01T00:00:00Z" },
      ] }),
      allHistory: vi.fn().mockResolvedValue({ history: [] }),
      history: vi.fn().mockResolvedValue({ history: [] }),
      create: vi.fn().mockResolvedValue({}),
      update: vi.fn().mockResolvedValue({}),
      delete: vi.fn().mockResolvedValue({}),
    },
  },
}));

describe("Triggers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra triggers", async () => {
    render(<Triggers />);
    expect(await screen.findByText("High CPU")).toBeInTheDocument();
  });

  it("abre create form", async () => {
    render(<Triggers />);
    await screen.findByText("High CPU");

    fireEvent.click(screen.getByText("+ New Trigger"));
    expect(await screen.findByText("Create Trigger Rule")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("ID *")).toBeInTheDocument();
  });
});
