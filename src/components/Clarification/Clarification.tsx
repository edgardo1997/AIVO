import { useState, useEffect } from "react";

interface ClarificationOption {
  id: string;
  label: string;
  meta?: string;
}

export interface ClarificationEvent {
  clarification_id: string;
  correlation_id: string;
  question: string;
  response_language: string;
  ambiguity_type: string;
  candidate_options: ClarificationOption[];
  allow_free_text: boolean;
  risk_if_wrong?: string;
  assumptions?: string[];
  expires_at?: string;
}

interface Props {
  event: ClarificationEvent;
  onResolve: (clarification_id: string, choice?: string, text?: string) => void;
  onCancel: (clarification_id: string) => void;
}

export function Clarification({ event, onResolve, onCancel }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    if (!event.expires_at) return;
    const expires = new Date(event.expires_at).getTime();
    const now = Date.now();
    if (now >= expires) {
      setStale(true);
      return;
    }
    const timer = setTimeout(() => setStale(true), expires - now);
    return () => clearTimeout(timer);
  }, [event.expires_at]);

  const handleSubmit = () => {
    if (stale) return;
    setSubmitting(true);
    if (event.allow_free_text && text.trim()) {
      onResolve(event.clarification_id, undefined, text.trim());
    } else if (selected) {
      onResolve(event.clarification_id, selected, undefined);
    } else {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="clarification"
      role="dialog"
      aria-modal="true"
      aria-label="Clarification request"
      style={{ padding: 16, background: "var(--surface-2)", borderRadius: 8 }}
    >
      <p style={{ marginBottom: 12, fontSize: 14 }}>{event.question}</p>
      {stale && (
        <p style={{ color: "var(--error)", fontSize: 12 }}>This clarification has expired.</p>
      )}
      {event.risk_if_wrong && (
        <p style={{ color: "var(--warning)", fontSize: 12, marginBottom: 12 }}>
          {event.risk_if_wrong}
        </p>
      )}
      <div role="radiogroup" aria-label="Clarification options">
        {event.candidate_options.map((opt) => (
          <label
            key={opt.id}
            style={{ display: "block", marginBottom: 8, cursor: stale ? "not-allowed" : "pointer" }}
          >
            <input
              type="radio"
              name={`clarify-${event.clarification_id}`}
              value={opt.id}
              checked={selected === opt.id}
              disabled={stale}
              onChange={() => setSelected(opt.id)}
              aria-label={`${opt.label} ${opt.meta || ""}`.trim()}
            />
            <span style={{ marginLeft: 8 }}>{opt.label}</span>
            {opt.meta && <span style={{ color: "var(--text-muted)", fontSize: 12, marginLeft: 8 }}>{opt.meta}</span>}
          </label>
        ))}
      </div>
      {event.allow_free_text && (
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={stale}
          placeholder="Or type your answer..."
          style={{ display: "block", width: "100%", marginTop: 12, padding: 8 }}
          aria-label="Free-text clarification"
        />
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <button
          className="btn btn-primary"
          onClick={handleSubmit}
          disabled={stale || submitting || (!selected && !(event.allow_free_text && text.trim()))}
          aria-busy={submitting}
        >
          {submitting ? "Submitting..." : "Confirm"}
        </button>
        <button className="btn btn-ghost" onClick={() => onCancel(event.clarification_id)} disabled={stale}>
          Cancel
        </button>
        {event.candidate_options.length > 0 && (
          <button className="btn btn-ghost" onClick={() => onResolve(event.clarification_id, "none", undefined)} disabled={stale}>
            None of these
          </button>
        )}
      </div>
    </div>
  );
}
