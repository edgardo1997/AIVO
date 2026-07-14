import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Sentinel } from "../components/Sentinel/Sentinel";

vi.mock("../api", () => ({
  api: {
    sentinel: {
      process: vi.fn().mockResolvedValue({
        approved: true, simulated: false, blocked: false, action_id: null, error: null,
        decision: "approved", decision_reason: "Safe operation",
        intent: { action: "monitor", target: "cpu", confidence: 0.95, raw_input: "show me cpu", parameters: {} },
        plan: { risk_score: 0.1, steps: [{ id: "step1", tool_id: "system.cpu", description: "Get CPU info", estimated_impact: "read-only", is_reversible: true }] },
        tool_result: { success: true, data: { percent: 45 }, error: null, duration_ms: 100, requires_confirmation: false },
        step_results: null, rollback_actions: null, context_factors: [], base_risk_score: null, context_modifier: null, final_risk_score: null, goal: null,
      }),
      approve: vi.fn().mockResolvedValue({
        approved: true, blocked: false, action_id: null, error: null, simulation_summary: "Approved",
        decision: "approved", intent: { action: "monitor", target: "cpu", confidence: 0.9, raw_input: "" },
        tool_result: { success: true, data: { percent: 45 }, error: null, duration_ms: 100, requires_confirmation: false },
        step_results: [], rollback_actions: [],
      }),
      approveModified: vi.fn().mockResolvedValue({
        approved: true, blocked: false, action_id: null, error: null, simulation_summary: "Modified and approved",
        decision: "approved", intent: { action: "monitor", target: "cpu", confidence: 0.9, raw_input: "" },
        tool_result: { success: true, data: {}, error: null, duration_ms: 100, requires_confirmation: false },
        step_results: [],
      }),
      reject: vi.fn().mockResolvedValue({}),
    },
  },
}));

import { api } from "../api";

describe("Sentinel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra IntentInput", async () => {
    render(<Sentinel />);
    expect(await screen.findByPlaceholderText("What do you want to do?")).toBeInTheDocument();
  });

  it("envía query", async () => {
    render(<Sentinel />);
    await screen.findByPlaceholderText("What do you want to do?");

    const input = screen.getByPlaceholderText("What do you want to do?");
    fireEvent.change(input, { target: { value: "show me cpu" } });
    fireEvent.click(screen.getByText("Go"));

    await waitFor(() => {
      expect(api.sentinel.process).toHaveBeenCalledWith("show me cpu", {});
    });
    expect(await screen.findByText("Get CPU info")).toBeInTheDocument();
    expect(screen.getByText("Safe operation")).toBeInTheDocument();
  });

  it("muestra dry-run checkbox", async () => {
    render(<Sentinel />);
    expect(await screen.findByText("Dry-run")).toBeInTheDocument();
  });
});
