import { useState, useRef, useEffect } from "react";
import { v1Api } from "../../api";
import { useAppState } from "../../contexts/AppContext";
import { ConfirmDialog } from "../ConfirmDialog";

export function Console() {
  const { permissionLevel } = useAppState();
  const [output, setOutput] = useState<string[]>([""]);
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingCmd, setPendingCmd] = useState("");
  const [pendingActionId, setPendingActionId] = useState("");
  const outRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    outRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [output]);

  const execute = async () => {
    const cmd = input.trim();
    if (!cmd) return;
    setOutput((o) => [...o, `> ${cmd}`]);
    setHistory((h) => [...h, cmd]);
    setHistoryIdx(-1);
    setInput("");
    try {
      const res = await v1Api.execute("executor.command", { command: cmd, timeout: 15 });
      if (res.requires_confirmation) {
        setPendingCmd(cmd);
        setPendingActionId(res.action_id || "");
        setConfirmOpen(true);
        setOutput((o) => [...o, `  \u26A0\uFE0F ${res.error || "Requires confirmation"}`, ""]);
        return;
      }
      appendOutput((res.data as any) || {});
    } catch (e) {
      setOutput((o) => [...o, `  Error: ${e}`, ""]);
    }
  };

  const handleConfirm = async () => {
    setConfirmOpen(false);
    try {
      const res = await v1Api.execute("executor.command", { command: pendingCmd, timeout: 15, confirmed: true, action_id: pendingActionId });
      appendOutput((res.data as any) || {});
    } catch (e) {
      setOutput((o) => [...o, `  Error: ${e}`, ""]);
    }
  };

  const handleDeny = () => {
    setConfirmOpen(false);
    setOutput((o) => [...o, `  \u26D4 Action denied by user`, ""]);
  };

  const appendOutput = (res: any) => {
    if (res.stdout) setOutput((o) => [...o, ...res.stdout.split("\n")]);
    if (res.stderr) setOutput((o) => [...o, ...[res.stderr].flat().map((l: string) => `  ${l}`)]);
    setOutput((o) => [...o, `  [Exit: ${res.returncode}]`, ""]);
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") { execute(); return; }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (history.length > 0) {
        const idx = historyIdx === -1 ? history.length - 1 : Math.max(0, historyIdx - 1);
        setHistoryIdx(idx);
        setInput(history[idx]);
      }
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIdx >= 0) {
        const idx = historyIdx + 1;
        if (idx >= history.length) { setHistoryIdx(-1); setInput(""); }
        else { setHistoryIdx(idx); setInput(history[idx]); }
      }
    }
  };

  const quickCommands = [
    { label: "Info Sistema", cmd: "systeminfo | findstr /B /C:\"OS Name\" /C:\"OS Version\"" },
    { label: "Red", cmd: "ipconfig | findstr IPv4" },
    { label: "Procesos", cmd: "tasklist /FI \"STATUS eq running\"" },
    { label: "Disco", cmd: "wmic logicaldisk get size,freespace,caption" },
  ];

  return (
    <div>
      <ConfirmDialog
        open={confirmOpen}
        title="\u26A0\uFE0F Confirmar Ejecución"
        message="Este comando requiere tu aprobación:"
        details={pendingCmd}
        onConfirm={handleConfirm}
        onDeny={handleDeny}
        onCancel={handleDeny}
      />
      <h2 style={{ marginBottom: 16, fontWeight: 600 }}>Consola</h2>
      <div style={{ marginBottom: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
        {quickCommands.map((qc) => (
          <button key={qc.label} className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => setInput(qc.cmd)}>
            {qc.label}
          </button>
        ))}
      </div>
      <div className="console-output" ref={outRef as any}>
        <div style={{ color: "var(--text-muted)", marginBottom: 4 }}>
          Consola Sentinel v1.0.0 &mdash; Nivel de permiso: {permissionLevel}
        </div>
        <hr style={{ border: "none", borderTop: "1px solid var(--border)", marginBottom: 8 }} />
        {output.map((line, i) => (
          <div key={i} className={line.includes("\u26A0") || line.includes("\u26D4") || line.includes("Error") ? "error" : ""}>
            {line || "\u00A0"}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <input
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="> escribe un comando..."
          style={{ fontFamily: "monospace" }}
        />
        <button className="btn btn-primary" onClick={execute}>Ejecutar</button>
        <button className="btn btn-ghost" onClick={() => setOutput([""])}>Limpiar</button>
      </div>
    </div>
  );
}
