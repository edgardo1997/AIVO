import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Memory } from "../components/Memory/Memory";

vi.mock("../api", () => ({
  api: {
    sentinel: {
      memorySessions: vi.fn().mockResolvedValue({ sessions: [
        { session_id: "sess1", created_at: "2024-01-15T10:00:00Z", updated_at: "2024-01-15T11:00:00Z", execution_count: 5, last_utterance: "Show me CPU" },
        { session_id: "sess2", created_at: "2024-01-14T10:00:00Z", updated_at: "2024-01-14T11:00:00Z", execution_count: 2, last_utterance: "List files" },
      ] }),
      memorySession: vi.fn().mockResolvedValue({ records: [
        { execution_id: "ex1", timestamp: "2024-01-15T10:30:00Z", utterance: "Show CPU", intent: { action: "monitor", target: "cpu" }, error: null },
      ] }),
      searchMemory: vi.fn().mockResolvedValue({ results: [] }),
      createMemorySession: vi.fn().mockResolvedValue({ session_id: "sess3" }),
      deleteMemorySession: vi.fn().mockResolvedValue({}),
    },
  },
}));

import { api } from "../api";

describe("Memory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra lista de sesiones", async () => {
    render(<Memory />);
    expect(await screen.findByText("Show me CPU")).toBeInTheDocument();
    expect(screen.getByText("List files")).toBeInTheDocument();
  });

  it("abre sesión al hacer click", async () => {
    render(<Memory />);
    await screen.findByText("Show me CPU");

    fireEvent.click(screen.getByText("Show me CPU"));

    await waitFor(() => {
      expect(api.sentinel.memorySession).toHaveBeenCalledWith("sess1");
    });
    expect(await screen.findByText("Show CPU")).toBeInTheDocument();
  });

  it("crea nueva sesión", async () => {
    render(<Memory />);
    await screen.findByText("Show me CPU");

    fireEvent.click(screen.getByText("Nueva sesión"));

    await waitFor(() => {
      expect(api.sentinel.createMemorySession).toHaveBeenCalled();
    });
  });
});
