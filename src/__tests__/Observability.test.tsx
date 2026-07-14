import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Observability } from "../components/Observability/Observability";

vi.mock("../api", () => ({
  api: {
    observability: {
      circuitBreakers: () => Promise.resolve({ circuits: [{ provider_id: "openai", state: "closed", consecutive_failures: 0, failure_threshold: 5, cooldown_seconds: 30, remaining_cooldown: 0 }] }),
      rateLimiter: () => Promise.resolve({ keys: {}, total_allowed: 100, total_denied: 5 }),
      feedback: () => Promise.resolve({ total_feedbacks: 50, by_provider: { openai: { count: 30, avg_duration_ms: 1200, success_rate: 0.95 } } }),
      costs: () => Promise.resolve({ total_cost: 0.025, total_tokens: 15000, by_provider: { openai: { cost: 0.025, tokens: 15000 } } }),
      performanceAlerts: () => Promise.resolve({ alerts: [{ id: "pa1", tool_id: "executor.command", metric: "duration", deviation: 0.5, severity: "medium", timestamp: "2024-01-15T10:00:00Z" }] }),
      fallbacks: () => Promise.resolve({ total_fallbacks: 10, successful_fallbacks: 8, by_tool: { executor: { attempts: 10, successes: 8 } } }),
      health: () => Promise.resolve({ tools: { executor: { healthy: true, state: "up", consecutive_failures: 0 } }, stats: {} }),
      alerts: () => Promise.resolve({ alerts: [] }),
      overview: () => Promise.resolve({ enabled: true, traces: { total_executions: 1000, active_spans: 5, success_rate: 0.98, latency_ms: { average: 200, p50: 150, p95: 500, maximum: 2000 }, quality: { blocked: 3, redacted: 1 }, errors_by_category: {} }, costs: { total_cost_usd: 0.05, total_tokens: 30000, total_calls: 100 }, alerts: { total: 0, unacknowledged: 0, by_source: {} } }),
      network: () => Promise.resolve({ online: true, last_check: "2024-01-15T10:00:00Z" }),
    },
  },
}));

describe("Observability", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra Trazas, Latencia, Calidad cards", async () => {
    render(<Observability />);
    expect(await screen.findByText("Trazas")).toBeInTheDocument();
    expect(screen.getByText("Latencia")).toBeInTheDocument();
    expect(screen.getByText("Calidad")).toBeInTheDocument();
  });

  it("muestra Tool Health", async () => {
    render(<Observability />);
    const executor = await screen.findAllByText("executor");
    expect(executor.length).toBeGreaterThan(0);
  });

  it("muestra Circuit Breakers", async () => {
    render(<Observability />);
    const openai = await screen.findAllByText("openai");
    expect(openai.length).toBeGreaterThan(0);
    expect(screen.getByText("closed")).toBeInTheDocument();
  });

  it("muestra Network Status", async () => {
    render(<Observability />);
    expect(await screen.findByText("Online")).toBeInTheDocument();
  });

  it("muestra Stats Summary", async () => {
    render(<Observability />);
    expect(await screen.findByText(/Feedbacks: 50/)).toBeInTheDocument();
    expect(screen.getByText(/Fallbacks: 10/)).toBeInTheDocument();
    expect(screen.getByText(/Cost: \$0.0250/)).toBeInTheDocument();
  });
});
