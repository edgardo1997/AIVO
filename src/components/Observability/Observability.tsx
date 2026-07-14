import { useCallback, useState } from "react";
import { api } from "../../api";
import { usePolling } from "../../hooks/usePolling";
import type {
  CircuitBreakerState, RateLimitStats, FeedbackStats, CostSummary,
  PerformanceAlert, FallbackStats, HealthStatus, AlertInfo, ObservabilityOverview, NetworkStatus,
} from "../../types";

const severityColor: Record<string, string> = {
  critical: "red", high: "red", medium: "yellow", low: "green", info: "purple",
};

function fmtMs(ms: number): string {
  if (ms >= 1000) return (ms / 1000).toFixed(1) + "s";
  return ms.toFixed(0) + "ms";
}

export function Observability() {
  const [circuits, setCircuits] = useState<CircuitBreakerState[]>([]);
  const [rateLimit, setRateLimit] = useState<RateLimitStats | null>(null);
  const [feedback, setFeedback] = useState<FeedbackStats | null>(null);
  const [costs, setCosts] = useState<CostSummary | null>(null);
  const [perfAlerts, setPerfAlerts] = useState<PerformanceAlert[]>([]);
  const [fallbacks, setFallbacks] = useState<FallbackStats | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [alerts, setAlerts] = useState<AlertInfo[]>([]);
  const [overview, setOverview] = useState<ObservabilityOverview | null>(null);
  const [network, setNetwork] = useState<NetworkStatus | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [cb, rl, fb, co, pa, fl, he, al, ov, nw] = await Promise.all([
        api.observability.circuitBreakers(),
        api.observability.rateLimiter(),
        api.observability.feedback(),
        api.observability.costs(),
        api.observability.performanceAlerts(),
        api.observability.fallbacks(),
        api.observability.health(),
        api.observability.alerts(),
        api.observability.overview(),
        api.observability.network(),
      ]);
      setCircuits(cb.circuits ?? []);
      setRateLimit(rl);
      setFeedback(fb);
      setCosts(co);
      setPerfAlerts(pa.alerts ?? []);
      setFallbacks(fl);
      setHealth(he);
      setAlerts(al.alerts ?? []);
      setOverview(ov);
      setNetwork(nw);
    } catch {}
  }, []);

  usePolling(fetchAll, 5000);

  const hasAlerts = alerts.length > 0 || perfAlerts.length > 0;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h2 style={{ fontWeight: 600 }}>Observability</h2>
        {hasAlerts && (
          <span className="status-emergency">
            {alerts.length + perfAlerts.length} alert{alerts.length + perfAlerts.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <div className="grid-3" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card-title">Trazas</div>
          <div className="metric-value">{overview?.traces.total_executions ?? 0}</div>
          <div className="text-muted">Éxito {overview?.traces.success_rate.toFixed(1) ?? "100.0"}% · {overview?.traces.active_spans ?? 0} activas</div>
        </div>
        <div className="card">
          <div className="card-title">Latencia</div>
          <div className="metric-value">{fmtMs(overview?.traces.latency_ms.p95 ?? 0)}</div>
          <div className="text-muted">p50 {fmtMs(overview?.traces.latency_ms.p50 ?? 0)} · promedio {fmtMs(overview?.traces.latency_ms.average ?? 0)}</div>
        </div>
        <div className="card">
          <div className="card-title">Calidad</div>
          <div className="metric-value">{overview?.traces.quality.blocked ?? 0}</div>
          <div className="text-muted">bloqueadas · {overview?.traces.quality.redacted ?? 0} redactadas</div>
        </div>
      </div>

      {/* Health + Alerts row */}
      <div className="grid-3">
        <div className="card">
          <div className="card-title">Tool Health</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            {health ? (
              <div className="metric-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                {Object.entries(health.tools).slice(0, 12).map(([id, t]) => (
                  <div key={id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span className={`status-dot ${t.healthy ? "ok" : "bad"}`} />
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{id}</span>
                  </div>
                ))}
              </div>
            ) : <span className="analysis-empty">Loading...</span>}
          </div>
        </div>

        <div className="card">
          <div className="card-title">Alerts</div>
          <div className="action-stack" style={{ maxHeight: 180, overflowY: "auto" }}>
            {alerts.length === 0 && perfAlerts.length === 0 && (
              <span className="analysis-empty">No active alerts</span>
            )}
            {alerts.slice(0, 10).map((a) => (
              <div key={a.id} style={{ fontSize: 11, display: "flex", gap: 6, alignItems: "flex-start" }}>
                <span className={`status-dot ${severityColor[a.severity] || "green"}`} />
                <span style={{ color: "var(--text-secondary)" }}>{a.message}</span>
              </div>
            ))}
            {perfAlerts.slice(0, Math.max(0, 10 - alerts.length)).map((a, i) => (
              <div key={`perf-${i}`} style={{ fontSize: 11, display: "flex", gap: 6, alignItems: "flex-start" }}>
                <span className={`status-dot ${severityColor[a.severity] || "green"}`} />
                <span style={{ color: "var(--text-secondary)" }}>{a.tool_id}: {a.metric} +{(a.deviation * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-title">Stats Summary</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 6 }}>
            <div>Feedbacks: {feedback?.total_feedbacks ?? "—"}</div>
            <div>Fallbacks: {fallbacks?.total_fallbacks ?? "—"} ({fallbacks?.successful_fallbacks ?? 0} ok)</div>
            <div>Cost: ${costs?.total_cost?.toFixed(4) ?? "—"} ({costs?.total_tokens ?? 0} tokens)</div>
            <div>Rate-limited: {rateLimit?.total_denied ?? 0} denied / {rateLimit?.total_allowed ?? 0} allowed</div>
          </div>
        </div>
      </div>

      {/* Circuit breakers */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Circuit Breakers</div>
        {circuits.length === 0 ? (
          <span className="analysis-empty">No circuit breakers</span>
        ) : (
          <table className="process-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>State</th>
                <th>Failures</th>
                <th>Threshold</th>
                <th>Cooldown</th>
              </tr>
            </thead>
            <tbody>
              {circuits.map((c) => (
                <tr key={c.provider_id}>
                  <td>{c.provider_id}</td>
                  <td>
                    <span className={`status-dot ${c.state === "closed" ? "ok" : c.state === "half-open" ? "warn" : "bad"}`} />
                    {" "}{c.state}
                  </td>
                  <td>{c.consecutive_failures} / {c.failure_threshold}</td>
                  <td>{c.cooldown_seconds}s</td>
                  <td>{c.remaining_cooldown > 0 ? `${c.remaining_cooldown}s` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Provider feedback & costs side by side */}
      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card-title">Provider Feedback</div>
          {feedback?.by_provider ? (
            <table className="process-table">
              <thead>
                <tr><th>Provider</th><th>Calls</th><th>Avg Duration</th><th>Success</th></tr>
              </thead>
              <tbody>
                {Object.entries(feedback.by_provider).map(([p, s]) => (
                  <tr key={p}>
                    <td>{p}</td><td>{s.count}</td>
                    <td>{fmtMs(s.avg_duration_ms)}</td>
                    <td>{(s.success_rate * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <span className="analysis-empty">No feedback data</span>}
        </div>

        <div className="card">
          <div className="card-title">Cost Breakdown</div>
          {costs?.by_provider ? (
            <table className="process-table">
              <thead>
                <tr><th>Provider</th><th>Cost</th><th>Tokens</th></tr>
              </thead>
              <tbody>
                {Object.entries(costs.by_provider).map(([p, s]) => (
                  <tr key={p}>
                    <td>{p}</td>
                    <td>${s.cost.toFixed(4)}</td>
                    <td>{s.tokens.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <span className="analysis-empty">No cost data</span>}
        </div>
      </div>

      {/* Performance alerts + Fallbacks */}
      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card-title">Performance Alerts</div>
          {perfAlerts.length === 0 ? (
            <span className="analysis-empty">None</span>
          ) : (
            <div className="action-stack" style={{ maxHeight: 200, overflowY: "auto" }}>
              {perfAlerts.map((a, i) => (
                <div key={i} style={{ fontSize: 12, borderLeft: "3px solid var(--danger)", paddingLeft: 8 }}>
                  <div style={{ color: "var(--text-secondary)" }}>{a.tool_id}: {a.metric} +{(a.deviation * 100).toFixed(0)}%</div>
                  <div style={{ color: "var(--text-muted)", fontSize: 10 }}>{a.severity} — {a.timestamp}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title">Fallback Stats</div>
          {fallbacks?.by_tool ? (
            <table className="process-table">
              <thead>
                <tr><th>Tool</th><th>Attempts</th><th>Successes</th><th>Rate</th></tr>
              </thead>
              <tbody>
                {Object.entries(fallbacks.by_tool).map(([t, s]) => (
                  <tr key={t}>
                    <td>{t}</td><td>{s.attempts}</td><td>{s.successes}</td>
                    <td>{s.attempts > 0 ? ((s.successes / s.attempts) * 100).toFixed(0) : "—"}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <span className="analysis-empty">No fallback data</span>}
        </div>
      </div>

      {/* Network Status */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Network Status</div>
        {network ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <span className={`status-dot ${network.online ? "ok" : "bad"}`} />
            <span>{network.online ? "Online" : "Offline"}</span>
            {network.last_check && (
              <span style={{ color: "var(--text-muted)", fontSize: 11, marginLeft: 8 }}>
                Last check: {new Date(network.last_check).toLocaleString()}
              </span>
            )}
          </div>
        ) : (
          <span className="analysis-empty">Loading...</span>
        )}
      </div>

      {/* Rate limit detail */}
      <div className="card">
        <div className="card-title">Rate Limiter</div>
        {rateLimit && Object.keys(rateLimit.keys).length > 0 ? (
          <table className="process-table">
            <thead>
              <tr><th>Key</th><th>Allowed</th><th>Denied</th><th>Limit</th><th>Window</th></tr>
            </thead>
            <tbody>
              {Object.entries(rateLimit.keys).slice(0, 20).map(([k, s]) => (
                <tr key={k}>
                  <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{k}</td>
                  <td>{s.allowed}</td>
                  <td>{s.denied}</td>
                  <td>{s.limit}</td>
                  <td>{s.window_seconds}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <span className="analysis-empty">No rate limit keys</span>}
      </div>
    </div>
  );
}
