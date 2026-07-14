import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Audit } from "../components/Audit/Audit";

vi.mock("../api", () => ({
  v1Api: {
    listAudit: vi.fn().mockResolvedValue({
      entries: [
        { id: 1, timestamp: "2024-01-15T10:30:00Z", action: "pipeline.execute", status: "success", user: "admin", details: "Executed system.info", event_id: "evt1", execution_id: "ex1", entry_hash: "abc123def456", previous_hash: "prevhash" },
        { id: 2, timestamp: "2024-01-15T10:31:00Z", action: "executor.command", status: "blocked", user: "admin", details: "Blocked dangerous command", event_id: "evt2", execution_id: "ex2", entry_hash: "def789ghi012", previous_hash: "abc123def456" },
      ],
      total: 2,
    }),
    verifyAuditIntegrity: vi.fn().mockResolvedValue({ valid: true, entries: 2, head: "def789ghi012" }),
  },
}));

describe("Audit", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra audit entries", async () => {
    render(<Audit />);
    expect(await screen.findByText("pipeline.execute")).toBeInTheDocument();
    expect(screen.getByText("executor.command")).toBeInTheDocument();
  });

  it("muestra integrity badge", async () => {
    render(<Audit />);
    expect(await screen.findByText(/Chain verified/)).toBeInTheDocument();
  });

  it("expande timeline entry", async () => {
    render(<Audit />);
    await screen.findByText("pipeline.execute");

    const entries = screen.getAllByText(/pipeline\.execute|executor\.command/);
    fireEvent.click(entries[0]);

    await waitFor(() => {
      expect(screen.getByText(/Event ID/)).toBeInTheDocument();
    });
    expect(screen.getByText(/evt1/)).toBeInTheDocument();
    expect(screen.getByText(/ex1/)).toBeInTheDocument();
  });
});
