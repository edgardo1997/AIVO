import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FeedbackCosts } from "../components/FeedbackCosts/FeedbackCosts";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    feedbackCosts: {
      stats: vi.fn(), records: vi.fn(), summary: vi.fn(), total: vi.fn(),
      budgets: vi.fn(), createBudget: vi.fn(), deleteBudget: vi.fn(),
    },
  },
}));

const feedbackApi = api.feedbackCosts;

function mockDashboard() {
  vi.mocked(feedbackApi.stats).mockResolvedValue({
    stats: [{ provider_id: "openai", task_type: "reasoning", total: 4, successes: 3, failures: 1, avg_duration_ms: 1200, success_rate: 0.75 }],
  });
  vi.mocked(feedbackApi.records).mockResolvedValue({ records: [] });
  vi.mocked(feedbackApi.summary).mockResolvedValue({
    summary: [{ provider_id: "openai", model: "gpt-test", total_calls: 4, total_prompt_tokens: 600, total_completion_tokens: 400, total_tokens: 1000, total_cost_usd: 0.25 }],
  });
  vi.mocked(feedbackApi.total).mockResolvedValue({ total_cost_usd: 0.25, total_tokens: 1000 });
  vi.mocked(feedbackApi.budgets).mockResolvedValue({ budgets: [] });
}

describe("FeedbackCosts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDashboard();
  });

  it("muestra costos y calidad obtenidos del backend", async () => {
    render(<FeedbackCosts />);

    expect(await screen.findByText("gpt-test")).toBeInTheDocument();
    expect(screen.getByText("reasoning")).toBeInTheDocument();
    expect(screen.getByText("75.0%")).toBeInTheDocument();
    expect(screen.getAllByText("1,000").length).toBeGreaterThan(0);
  });

  it("crea un presupuesto y actualiza los datos", async () => {
    vi.mocked(feedbackApi.createBudget).mockResolvedValue({ success: true, name: "mensual" });
    render(<FeedbackCosts />);
    await screen.findByText("gpt-test");

    fireEvent.change(screen.getByLabelText("Nombre del presupuesto"), { target: { value: "mensual" } });
    fireEvent.change(screen.getByLabelText("Límite en dólares"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Agregar" }));

    await waitFor(() => expect(feedbackApi.createBudget).toHaveBeenCalledWith({
      name: "mensual", max_cost_usd: 10, period: "monthly",
    }));
    expect(feedbackApi.total).toHaveBeenCalledTimes(2);
  });
});
