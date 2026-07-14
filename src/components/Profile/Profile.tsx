import { useState, useEffect, useRef } from "react";
import { api } from "../../api";
import type { ProfilePreset, ProfileHistoryEntry } from "../../types";

interface ProfileData {
  user_id: string;
  username: string;
  display_name: string;
  avatar: string;
  theme: string;
  timezone: string;
  locale: string;
}

interface IdentityData {
  user_id: string;
  username: string;
  role: string;
  is_local: boolean;
}

export function Profile() {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [identity, setIdentity] = useState<IdentityData | null>(null);
  const [preferences, setPreferences] = useState<Record<string, unknown>>({});
  const [displayName, setDisplayName] = useState("");
  const [theme, setTheme] = useState("light");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [prefKey, setPrefKey] = useState("");
  const [prefValue, setPrefValue] = useState("");
  const [presets, setPresets] = useState<ProfilePreset[]>([]);
  const [presetName, setPresetName] = useState("");
  const [presetDesc, setPresetDesc] = useState("");
  const [presetMsg, setPresetMsg] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ProfileHistoryEntry[]>([]);
  const [searching, setSearching] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () => {
    api.profile.get().then((data) => {
      setProfile(data.profile as ProfileData);
      setIdentity(data.identity as IdentityData);
      setDisplayName((data.profile as ProfileData).display_name);
      setTheme((data.profile as ProfileData).theme);
      setPreferences(data.preferences as Record<string, unknown>);
    });
    api.profile.presets().then(setPresets).catch(() => {});
  };

  useEffect(refresh, []);

  const saveProfile = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await api.profile.update({ display_name: displayName, theme });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {}
    setSaving(false);
  };

  const addPreference = async () => {
    if (!prefKey) return;
    try {
      await api.profile.setPreference(prefKey, prefValue);
      setPreferences((p) => ({ ...p, [prefKey]: prefValue }));
      setPrefKey("");
      setPrefValue("");
    } catch {}
  };

  const delPreference = async (key: string) => {
    try {
      await api.profile.deletePreference(key);
      setPreferences((p) => {
        const next = { ...p };
        delete next[key];
        return next;
      });
    } catch {}
  };

  const handleExport = async () => {
    try {
      const data = await api.profile.export();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `profile-export-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {}
  };

  const handleImport = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      await api.profile.import(JSON.parse(text));
      refresh();
    } catch {}
    if (fileRef.current) fileRef.current.value = "";
  };

  const savePreset = async () => {
    if (!presetName.trim()) return;
    try {
      await api.profile.savePreset(presetName.trim(), presetDesc.trim());
      setPresetName("");
      setPresetDesc("");
      setPresetMsg("Preset saved");
      setTimeout(() => setPresetMsg(""), 2000);
      const p = await api.profile.presets();
      setPresets(p);
    } catch {
      setPresetMsg("Error saving preset");
      setTimeout(() => setPresetMsg(""), 2000);
    }
  };

  const applyPreset = async (name: string) => {
    try {
      await api.profile.applyPreset(name);
      await api.profile.get().then((data) => {
        setDisplayName((data.profile as ProfileData).display_name);
        setTheme((data.profile as ProfileData).theme);
        setPreferences(data.preferences as Record<string, unknown>);
      });
    } catch {}
  };

  const deletePreset = async (name: string) => {
    try {
      await api.profile.deletePreset(name);
      const p = await api.profile.presets();
      setPresets(p);
    } catch {}
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await api.profile.search(searchQuery.trim(), 20);
      setSearchResults(res);
    } catch {}
    setSearching(false);
  };

  return (
    <div className="profile-page">
      <h2 style={{ marginBottom: 16, fontWeight: 600 }}>Profile</h2>

      {identity && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Identity</div>
          <div style={{ fontSize: 13, lineHeight: 1.8 }}>
            <div><strong>User ID:</strong> {identity.user_id}</div>
            <div><strong>Role:</strong> {identity.role}</div>
            <div><strong>Local:</strong> {identity.is_local ? "Yes" : "No"}</div>
          </div>
        </div>
      )}

      {profile && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Profile</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 12 }}>
            <label style={{ fontSize: 12, fontWeight: 500 }}>
              Display Name
              <input
                className="input"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                style={{ marginTop: 4 }}
              />
            </label>
            <label style={{ fontSize: 12, fontWeight: 500 }}>
              Theme
              <select className="input" value={theme} onChange={(e) => setTheme(e.target.value)} style={{ marginTop: 4 }}>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            <button className="btn btn-primary" onClick={saveProfile} disabled={saving} style={{ alignSelf: "flex-start" }}>
              {saving ? "Saving..." : saved ? "Saved!" : "Save"}
            </button>
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Preferences</div>
        <div style={{ display: "flex", gap: 8, marginTop: 12, marginBottom: 12 }}>
          <input className="input" placeholder="Key" value={prefKey} onChange={(e) => setPrefKey(e.target.value)} style={{ flex: 1 }} />
          <input className="input" placeholder="Value" value={prefValue} onChange={(e) => setPrefValue(e.target.value)} style={{ flex: 1 }} />
          <button className="btn btn-primary" onClick={addPreference} disabled={!prefKey}>Add</button>
        </div>
        {Object.keys(preferences).length === 0 ? (
          <div style={{ fontSize: 13, color: "#888" }}>No preferences set.</div>
        ) : (
          <div style={{ fontSize: 13 }}>
            {Object.entries(preferences).map(([key, value]) => (
              <div key={key} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #eee" }}>
                <span><strong>{key}:</strong> {typeof value === "string" ? value : JSON.stringify(value)}</span>
                <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => delPreference(key)}>×</button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Export / Import */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Export / Import</div>
        <div style={{ display: "flex", gap: 12, marginTop: 12, alignItems: "center" }}>
          <button className="btn btn-primary" onClick={handleExport}>Export Profile</button>
          <input ref={fileRef} type="file" accept=".json" style={{ fontSize: 12, flex: 1 }} />
          <button className="btn btn-ghost" onClick={handleImport}>Import</button>
        </div>
      </div>

      {/* Presets */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Presets</div>
        <div style={{ display: "flex", gap: 8, marginTop: 12, marginBottom: 12 }}>
          <input className="input" placeholder="Preset name" value={presetName}
            onChange={(e) => setPresetName(e.target.value)} style={{ flex: 1 }} />
          <input className="input" placeholder="Description (optional)" value={presetDesc}
            onChange={(e) => setPresetDesc(e.target.value)} style={{ flex: 1 }} />
          <button className="btn btn-primary" onClick={savePreset} disabled={!presetName.trim()}>Save</button>
        </div>
        {presetMsg && <div style={{ fontSize: 11, color: presetMsg === "Preset saved" ? "var(--success, #22c55e)" : "var(--danger)", marginBottom: 8 }}>{presetMsg}</div>}
        {presets.length === 0 ? (
          <div style={{ fontSize: 13, color: "#888" }}>No presets saved.</div>
        ) : (
          <div style={{ fontSize: 13 }}>
            {presets.map((p) => (
              <div key={p.preset_name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #eee" }}>
                <div>
                  <strong>{p.preset_name}</strong>
                  {p.description && <span style={{ color: "#888", marginLeft: 8 }}>{p.description}</span>}
                  <div style={{ fontSize: 10, color: "#aaa" }}>{p.created_at}</div>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                  <button className="btn btn-ghost" style={{ fontSize: 10, padding: "2px 8px" }} onClick={() => applyPreset(p.preset_name)}>Apply</button>
                  <button className="btn btn-ghost" style={{ fontSize: 10, padding: "2px 8px", color: "var(--danger)" }} onClick={() => deletePreset(p.preset_name)}>Del</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* History Search */}
      <div className="card">
        <div className="card-title">History Search</div>
        <div style={{ display: "flex", gap: 8, marginTop: 12, marginBottom: 12 }}>
          <input className="input" placeholder="Search profile history..." value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            style={{ flex: 1 }} />
          <button className="btn btn-primary" onClick={handleSearch} disabled={searching}>
            {searching ? "Searching..." : "Search"}
          </button>
        </div>
        {searchResults.length > 0 && (
          <div style={{ fontSize: 12, maxHeight: 300, overflowY: "auto" }}>
            {searchResults.map((e, i) => (
              <div key={i} style={{ padding: "6px 0", borderBottom: "1px solid #eee" }}>
                <div><strong>{e.field}:</strong> {e.old_value} → {e.new_value}</div>
                <div style={{ color: "#aaa", fontSize: 10 }}>{e.changed_at}</div>
              </div>
            ))}
          </div>
        )}
        {searchResults.length === 0 && searchQuery && !searching && (
          <div style={{ fontSize: 13, color: "#888" }}>No results found.</div>
        )}
      </div>
    </div>
  );
}
