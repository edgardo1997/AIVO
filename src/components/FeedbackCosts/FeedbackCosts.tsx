import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../../api";
import type {
  CostBudget,
  CostTotal,
  ModelCostRow,
  ModelFeedbackRecord,
  ModelFeedbackStat,
} from "../../types";

const EMPTY_TOTAL: CostTotal = { total_cost_usd: 0, total_tokens: 0 };

function money(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value < 0.01 ? 4 : 2,
  }).format(value);
}

function duration(ms: number) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms.toFixed(0)} ms`;
}

export function FeedbackCosts() {
  const [stats, setStats] = useState<ModelFeedbackStat[]>([]);
  const [records, setRecords] = useState<ModelFeedbackRecord[]>([]);
  const [costs, setCosts] = useState<ModelCostRow[]>([]);
  const [total, setTotal] = useState<CostTotal>(EMPTY_TOTAL);
  const [budgets, setBudgets] = useState<CostBudget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [budgetName, setBudgetName] = useState("");
  const [budgetAmount, setBudgetAmount] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [feedbackStats, feedbackRecords, costSummary, costTotal, budgetList] = await Promise.all([
        api.feedbackCosts.stats(),
        api.feedbackCosts.records(),
        api.feedbackCosts.summary(),
        api.feedbackCosts.total(),
        api.feedbackCosts.budgets(),
      ]);
      setStats(feedbackStats.stats ?? []);
      setRecords((feedbackRecords.records ?? []).reverse());
      setCosts(costSummary.summary ?? []);
      setTotal(costTotal);
      setBudgets(budgetList.budgets ?? []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron cargar los datos");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const success = useMemo(() => {
    const attempts = stats.reduce((sum, item) => sum + item.total, 0);
    const successes = stats.reduce((sum, item) => sum + item.successes, 0);
    return { attempts, rate: attempts ? successes / attempts : 0 };
  }, [stats]);

  async function addBudget(event: FormEvent) {
    event.preventDefault();
    const amount = Number(budgetAmount);
    if (!budgetName.trim() || !Number.isFinite(amount) || amount <= 0) {
      setError("Escribe un nombre y un límite mayor que cero.");
      return;
    }
    try {
      await api.feedbackCosts.createBudget({
        name: budgetName.trim(), max_cost_usd: amount, period: "monthly",
      });
      setBudgetName("");
      setBudgetAmount("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar el presupuesto");
    }
  }

  async function removeBudget(name: string) {
    try {
      await api.feedbackCosts.deleteBudget(name);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo eliminar el presupuesto");
    }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontWeight: 600 }}>Feedback / Costos</h2>
          <div className="text-muted">Eficacia, latencia y gasto de los modelos que coordina Sentinel.</div>
        </div>
        <button className="btn-secondary" onClick={() => void load()} disabled={loading}>Actualizar</button>
      </div>

      {error && <div className="error-message" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="metric-grid" style={{ marginBottom: 16 }}>
        <div className="metric"><div className="metric-label">Costo total</div><div className="metric-value">{money(total.total_cost_usd)}</div></div>
        <div className="metric"><div className="metric-label">Tokens</div><div className="metric-value">{total.total_tokens.toLocaleString()}</div></div>
        <div className="metric"><div className="metric-label">Ejecuciones evaluadas</div><div className="metric-value">{success.attempts}</div></div>
        <div className="metric"><div className="metric-label">Tasa de éxito</div><div className="metric-value">{(success.rate * 100).toFixed(1)}%</div></div>
      </div>

      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card-title">Costo por modelo</div>
          {costs.length ? <table className="process-table"><thead><tr><th>Proveedor / modelo</th><th>Llamadas</th><th>Tokens</th><th>Costo</th></tr></thead><tbody>
            {costs.map((row) => <tr key={`${row.provider_id}:${row.model}`}><td>{row.provider_id}<div className="text-muted">{row.model}</div></td><td>{row.total_calls}</td><td>{row.total_tokens.toLocaleString()}</td><td>{money(row.total_cost_usd)}</td></tr>)}
          </tbody></table> : <span className="analysis-empty">Aún no hay consumo registrado.</span>}
        </div>
        <div className="card">
          <div className="card-title">Calidad por tipo de tarea</div>
          {stats.length ? <table className="process-table"><thead><tr><th>Proveedor / tarea</th><th>Intentos</th><th>Éxito</th><th>Latencia</th></tr></thead><tbody>
            {stats.map((row) => <tr key={`${row.provider_id}:${row.task_type}`}><td>{row.provider_id}<div className="text-muted">{row.task_type}</div></td><td>{row.total}</td><td>{(row.success_rate * 100).toFixed(0)}%</td><td>{duration(row.avg_duration_ms)}</td></tr>)}
          </tbody></table> : <span className="analysis-empty">Aún no hay feedback registrado.</span>}
        </div>
      </div>

      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card-title">Presupuestos mensuales</div>
          <form onSubmit={addBudget} style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <input value={budgetName} onChange={(e) => setBudgetName(e.target.value)} placeholder="Nombre" aria-label="Nombre del presupuesto" />
            <input value={budgetAmount} onChange={(e) => setBudgetAmount(e.target.value)} placeholder="USD" type="number" min="0.01" step="0.01" aria-label="Límite en dólares" />
            <button className="btn-primary" type="submit">Agregar</button>
          </form>
          {budgets.map((budget) => <div key={budget.name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderTop: "1px solid var(--border)" }}><span>{budget.name}<span className="text-muted"> · {money(budget.max_cost_usd)} / {budget.period}</span></span><button className="btn-secondary" onClick={() => void removeBudget(budget.name)}>Eliminar</button></div>)}
          {!budgets.length && <span className="analysis-empty">Sin presupuestos configurados.</span>}
        </div>
        <div className="card">
          <div className="card-title">Actividad reciente</div>
          <div className="action-stack" style={{ maxHeight: 280, overflowY: "auto" }}>
            {records.slice(0, 20).map((record, index) => <div key={`${record.timestamp}:${index}`} style={{ borderLeft: `3px solid ${record.success ? "var(--success)" : "var(--danger)"}`, paddingLeft: 8 }}><div>{record.provider_id} · {record.model}</div><div className="text-muted">{record.task_type} · {duration(record.duration_ms)} · {new Date(record.timestamp).toLocaleString()}</div>{record.error && <div className="error-message">{record.error}</div>}</div>)}
            {!records.length && <span className="analysis-empty">Sin actividad reciente.</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
