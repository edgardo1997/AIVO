import { useState, useEffect, useCallback } from "react";
import { api } from "../../api";
import type { HelpTopic, HelpCategory } from "../../types";

export function Help() {
  const [topics, setTopics] = useState<HelpTopic[]>([]);
  const [categories, setCategories] = useState<HelpCategory[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<HelpTopic | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const refresh = useCallback(async (category?: string) => {
    setLoading(true);
    try {
      const res = await api.help.topics(category || undefined);
      setTopics(res.topics);
      setCategories(res.categories);
      setLoading(false);
    } catch { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleCategoryChange = (catId: string | null) => {
    setActiveCategory(catId);
    setSelectedTopic(null);
    refresh(catId || undefined);
  };

  const handleSelectTopic = async (id: string) => {
    try {
      const topic = await api.help.topic(id);
      setSelectedTopic(topic);
    } catch { /* ignore */ }
  };

  const filteredTopics = search.trim()
    ? topics.filter((t) => t.title.toLowerCase().includes(search.toLowerCase()))
    : topics;

  return (
    <div style={{ display: "flex", gap: 16, height: "calc(100vh - 100px)", maxWidth: 1000 }}>
      <div style={{ width: 280, minWidth: 200, display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="card" style={{ padding: 12 }}>
          <div className="card-title" style={{ marginBottom: 8 }}>Documentation</div>
          <input
            className="chat-input"
            style={{ width: "100%", boxSizing: "border-box" }}
            placeholder="Search topics..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="card" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4 }}>
          <button
            className={`btn ${activeCategory === null ? "btn-primary" : "btn-ghost"}`}
            style={{ fontSize: 12, textAlign: "left", justifyContent: "flex-start" }}
            onClick={() => handleCategoryChange(null)}
          >All Topics</button>
          {categories.sort((a, b) => a.order - b.order).map((cat) => (
            <button
              key={cat.id}
              className={`btn ${activeCategory === cat.id ? "btn-primary" : "btn-ghost"}`}
              style={{ fontSize: 12, textAlign: "left", justifyContent: "flex-start" }}
              onClick={() => handleCategoryChange(cat.id)}
            >{cat.icon} {cat.title}</button>
          ))}
        </div>

        <div className="card" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4 }}>
          <div className="card-title" style={{ marginBottom: 4, fontSize: 11 }}>External Docs</div>
          <a href="docs/getting-started.md" target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--accent)" }}>Getting Started Guide</a>
          <a href="docs/policies-guide.md" target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--accent)" }}>Policies Guide</a>
          <a href="docs/api-reference.md" target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--accent)" }}>API Reference</a>
          <a href="docs/deployment.md" target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--accent)" }}>Deployment Guide</a>
          <a href="README.md" target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--accent)" }}>README</a>
        </div>
      </div>

      <div style={{ flex: 1, overflow: "auto" }}>
        {loading && <div className="loading">Loading...</div>}

        {!loading && selectedTopic && (
          <div className="card" style={{ padding: 24 }}>
            <button className="btn btn-ghost" style={{ fontSize: 12, marginBottom: 16 }} onClick={() => setSelectedTopic(null)}>← Back to topics</button>
            <div style={{ fontSize: 32, marginBottom: 12 }}>{selectedTopic.icon}</div>
            <h3 style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>{selectedTopic.title}</h3>
            <div style={{ fontSize: 14, lineHeight: 1.8, whiteSpace: "pre-wrap", color: "var(--text-secondary)" }}>
              {selectedTopic.content}
            </div>
          </div>
        )}

        {!loading && !selectedTopic && filteredTopics.length === 0 && (
          <div className="card" style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
            {search ? "No topics match your search." : "No documentation topics available."}
          </div>
        )}

        {!loading && !selectedTopic && filteredTopics.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {filteredTopics.map((t) => (
              <div
                key={t.id}
                className="card"
                style={{ padding: 16, cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }}
                onClick={() => handleSelectTopic(t.id)}
              >
                <span style={{ fontSize: 24 }}>{t.icon}</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{t.title}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                    {t.category}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
