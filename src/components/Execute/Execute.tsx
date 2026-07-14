import { useState } from "react";
import { v1Api } from "../../api";
import type { V1ExecuteResponse } from "../../types";

export function Execute() {
  const [toolId, setToolId] = useState("executor.command");
  const [params, setParams] = useState('{\n  "command": "echo hello"\n}');
  const [result, setResult] = useState<V1ExecuteResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleExecute = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const parsed = JSON.parse(params);
      const res = await v1Api.execute(toolId, parsed);
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Execution failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="execute-screen">
      <h2>Execute Tool</h2>
      <div className="execute-layout">
        <div className="execute-form">
          <label>Tool ID</label>
          <select value={toolId} onChange={(e) => setToolId(e.target.value)}>
            <option value="executor.command">executor.command</option>
            <option value="executor.launch">executor.launch</option>
            <option value="executor.kill">executor.kill</option>
            <option value="filesystem.read">filesystem.read</option>
            <option value="filesystem.write">filesystem.write</option>
            <option value="filesystem.list">filesystem.list</option>
            <option value="filesystem.search">filesystem.search</option>
            <option value="system.info">system.info</option>
            <option value="system.cpu">system.cpu</option>
            <option value="system.processes">system.processes</option>
          </select>

          <label>Parameters (JSON)</label>
          <textarea
            value={params}
            onChange={(e) => setParams(e.target.value)}
            rows={8}
            className="params-editor"
          />

          <button onClick={handleExecute} disabled={loading} className="execute-btn">
            {loading ? "Executing..." : "Execute"}
          </button>

          {error && <div className="error-box">{error}</div>}

          {result && (
            <div className="result-box">
              <h3>Result</h3>
              <pre>{JSON.stringify(result.data ?? result, null, 2)}</pre>
            </div>
          )}
        </div>

        <div className="pipeline-visualization">
          <h3>Pipeline</h3>
          {result?.pipeline ? (
            <div className="pipeline-steps">
              <div className="pipeline-step passed">
                <span className="step-indicator">✓</span>
                <span className="step-label">Intent: {((result.pipeline as any)?.plan?.intent?.target ?? (result.pipeline as any)?.intent?.target) || "unknown"}</span>
              </div>
              <div className="pipeline-step passed">
                <span className="step-indicator">✓</span>
                <span className="step-label">
                  Decision: {((result.pipeline as any)?.decision?.decision) || ((result.pipeline as any)?.decision) || "N/A"}
                </span>
              </div>
              <div className={`pipeline-step ${result.success ? "passed" : "blocked"}`}>
                <span className="step-indicator">{result.success ? "✓" : "✗"}</span>
                <span className="step-label">Execution: {result.success ? "Passed" : "Failed"}</span>
              </div>
              <div className="pipeline-step passed">
                <span className="step-indicator">✓</span>
                <span className="step-label">
                  Confirmation: {result.requires_confirmation ? "Required" : "Not required"}
                </span>
              </div>
              {result.duration_ms != null && (
                <div className="pipeline-step passed">
                  <span className="step-indicator">✓</span>
                  <span className="step-label">Duration: {(result.duration_ms / 1000).toFixed(2)}s</span>
                </div>
              )}
              {result.error && (
                <div className="pipeline-step blocked">
                  <span className="step-indicator">✗</span>
                  <span className="step-label">Error: {result.error}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="pipeline-steps">
              <div className={`pipeline-step ${loading ? "active" : "pending"}`}>
                <span className="step-indicator">{loading ? "→" : "○"}</span>
                <span className="step-label">Awaiting execution...</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
