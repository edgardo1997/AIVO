import { useState, useCallback, useEffect } from "react";
import { api } from "../../api";
import type { TimelineTree, TimelineNode } from "../../types";

function fmtMs(ms: number): string {
  if (ms >= 1000) return (ms / 1000).toFixed(2) + "s";
  return ms.toFixed(0) + "ms";
}

function statusColor(status: string): string {
  switch (status) {
    case "completed": return "var(--success)";
    case "failed": return "var(--danger)";
    case "error": return "var(--danger)";
    case "in_progress": return "var(--accent)";
    default: return "var(--text-muted)";
  }
}

function TimelineNodeRow({ node, depth }: { node: TimelineNode; depth: number }) {
  return (
    <div className="tl-node" style={{ marginLeft: depth * 20 }}>
      <div className="tl-node-header">
        <span className="status-dot" style={{ backgroundColor: statusColor(node.status) }} />
        <span className="tl-node-label">{node.label}</span>
        <span className="tl-node-duration">{fmtMs(node.duration_ms)}</span>
        <span className="tl-node-status" style={{ color: statusColor(node.status) }}>
          {node.status}
        </span>
        <span className="tl-node-count">{node.events.length} events</span>
      </div>
      {node.events.map((ev, i) => (
        <div key={i} className="tl-event" style={{ marginLeft: depth * 20 + 16 }}>
          <span className="tl-event-type">{ev.event_type}</span>
          {ev.tool && <span className="tl-event-tool">{ev.tool}</span>}
          {ev.duration != null && <span className="tl-event-duration">{fmtMs(ev.duration * 1000)}</span>}
          {ev.message && <span className="tl-event-message">{ev.message}</span>}
        </div>
      ))}
    </div>
  );
}

export function DebugTimeline() {
  const [requestId, setRequestId] = useState("");
  const [timeline, setTimeline] = useState<TimelineTree | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState<string[]>([]);

  const search = useCallback(async (rid: string) => {
    if (!rid.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.pipelineMetrics.timeline(rid.trim());
      setTimeline(data);
      setSearched((prev) => [rid.trim(), ...prev].slice(0, 20));
    } catch {
      setError("Timeline not found or request failed");
      setTimeline(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (requestId === "" && searched.length > 0 && !timeline) {
      setRequestId(searched[0]);
    }
  }, [searched, requestId, timeline]);

  return (
    <div className="card">
      <div className="card-title">Debug Timeline</div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <input
          className="input"
          type="text"
          placeholder="Enter request_id..."
          value={requestId}
          onChange={(e) => setRequestId(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") search(requestId); }}
          style={{ flex: 1 }}
        />
        <button className="button" onClick={() => search(requestId)} disabled={loading}>
          {loading ? "..." : "Search"}
        </button>
      </div>

      {searched.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
          {searched.map((rid) => (
            <button
              key={rid}
              className="button button-small"
              onClick={() => { setRequestId(rid); search(rid); }}
              style={{ fontSize: 11 }}
            >
              {rid.slice(0, 12)}…
            </button>
          ))}
        </div>
      )}

      {error && <div className="text-danger" style={{ fontSize: 12, marginBottom: 8 }}>{error}</div>}

      {timeline && (
        <div className="tl-tree">
          <div className="tl-root">
            <span className="tl-root-id">Request: {timeline.request_id}</span>
          </div>
          {timeline.children.length === 0 ? (
            <div className="analysis-empty" style={{ padding: "8px 0" }}>No pipeline stages found</div>
          ) : (
            timeline.children.map((node, i) => (
              <TimelineNodeRow key={i} node={node} depth={0} />
            ))
          )}
        </div>
      )}

      {!timeline && !loading && !error && (
        <div className="analysis-empty">Search for a request_id to see its pipeline timeline</div>
      )}
    </div>
  );
}
