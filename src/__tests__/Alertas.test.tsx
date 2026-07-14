import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Alertas } from "../components/Alertas/Alertas";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    alertas: {
      list: vi.fn(),
      acknowledge: vi.fn(),
      check: vi.fn(),
      clear: vi.fn(),
      costAlerts: vi.fn(),
      perfAlerts: vi.fn(),
    },
  },
}));

const alertasApi = api.alertas;
const ts = "2026-07-14T12:00:00.000Z";

const mockAlerts = {
  alerts: [
    { id: "a1", alert_type: "budget_exceeded", severity: "warning", title: "Budget exceeded", message: "Cost $0.05 exceeds $0.01", source: "cost", timestamp: ts, acknowledged: false, data: {} },
    { id: "a2", alert_type: "performance_regression", severity: "critical", title: "Performance regression: executor.command", message: "avg 500ms vs baseline 100ms (+400%)", source: "performance", timestamp: ts, acknowledged: false, data: {} },
  ],
  stats: { total: 2, unacknowledged: 2, by_source: { cost: 1, performance: 1 }, max_alerts: 200 },
};

describe("Alertas", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(alertasApi.list).mockResolvedValue(mockAlerts);
    vi.mocked(alertasApi.costAlerts).mockResolvedValue({ alerts: [] });
    vi.mocked(alertasApi.perfAlerts).mockResolvedValue({ alerts: [] });
  });

  it("muestra alertas de la API", async () => {
    render(<Alertas />);
    expect(await screen.findByText("Budget exceeded")).toBeInTheDocument();
    expect(screen.getByText("Performance regression: executor.command")).toBeInTheDocument();
  });

  it("muestra estadísticas", async () => {
    render(<Alertas />);
    expect(await screen.findByText("2 total")).toBeInTheDocument();
    expect(screen.getByText("2 unacknowledged")).toBeInTheDocument();
  });

  it("acknowledge individual", async () => {
    vi.mocked(alertasApi.acknowledge).mockResolvedValue({ acknowledged: 1 });
    render(<Alertas />);
    await screen.findByText("Budget exceeded");

    const ackButtons = screen.getAllByText("Ack");
    fireEvent.click(ackButtons[0]);

    await waitFor(() => expect(alertasApi.acknowledge).toHaveBeenCalledWith("a1"));
  });

  it("Ack All acknowledgea todas", async () => {
    vi.mocked(alertasApi.acknowledge).mockResolvedValue({ acknowledged: 2 });
    render(<Alertas />);
    await screen.findByText("Budget exceeded");

    fireEvent.click(screen.getByText("Ack All"));
    await waitFor(() => expect(alertasApi.acknowledge).toHaveBeenCalledWith(undefined, undefined));
  });

  it("Check ejecuta verificación", async () => {
    vi.mocked(alertasApi.check).mockResolvedValue({ checked: true, new_alerts: 0, stats: mockAlerts.stats });
    render(<Alertas />);
    await screen.findByText("Budget exceeded");

    fireEvent.click(screen.getByText("Check"));
    await waitFor(() => expect(alertasApi.check).toHaveBeenCalled());
  });

  it("Clear limpia alertas", async () => {
    vi.mocked(alertasApi.clear).mockResolvedValue({ cleared: 2 });
    render(<Alertas />);
    await screen.findByText("Budget exceeded");

    fireEvent.click(screen.getByText("Clear"));
    await waitFor(() => expect(alertasApi.clear).toHaveBeenCalledWith(true));
  });

  it("toogle Cost Alerts panel", async () => {
    vi.mocked(alertasApi.costAlerts).mockResolvedValue({
      alerts: [{ budget_name: "test-budget", provider_id: "openai", current_cost: 0.5, max_cost: 1.0, current_tokens: 100, max_tokens: 200, period: "monthly" }],
    });
    render(<Alertas />);
    await screen.findByText("Budget exceeded");

    fireEvent.click(screen.getByRole("button", { name: /Cost/ }));
    expect(await screen.findByText("test-budget")).toBeInTheDocument();
  });

  it("muestra estado vacío cuando no hay alertas", async () => {
    vi.mocked(alertasApi.list).mockResolvedValue({ alerts: [], stats: { total: 0, unacknowledged: 0, by_source: {}, max_alerts: 200 } });
    render(<Alertas />);
    expect(await screen.findByText(/No alerts/)).toBeInTheDocument();
  });
});
