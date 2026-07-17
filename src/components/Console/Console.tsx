import { useState, useRef, useEffect } from "react";
import { api } from "../../api";
import { ConfirmDialog } from "../ConfirmDialog";
import { PageHeader, Button } from "../ui";

export function Console() {
  const [output, setOutput] = useState<string[]>([
    "AIVO Console v0.1.0 — Permission level: Confirm",
    "----------------------------------------",
    "",
  ]);
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
      const res = await api.executor.command(cmd, 15);
      if (res.needs_confirm) {
        setPendingCmd(cmd);
        setPendingActionId(res.action_id || "");

        setConfirmOpen(true);
        setOutput((o) => [...o, `  ⚠️ ${res.reason || "Requires confirmation"}`, ""]);
        return;
      }
      appendOutput(res);
    } catch (e) {
      setOutput((o) => [...o, `  Error: ${e}`, ""]);
    }
  };

  const handleConfirm = async () => {
    setConfirmOpen(false);
    try {
      const res = await api.executor.command(pendingCmd, 15, true, pendingActionId);
      appendOutput(res);
    } catch (e) {
      setOutput((o) => [...o, `  Error: ${e}`, ""]);
    }
  };

  const handleDeny = () => {
    setConfirmOpen(false);
    setOutput((o) => [...o, `  ⛔ Action denied by user`, ""]);
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
    { label: "System Info", cmd: "systeminfo | findstr /B /C:\"OS Name\" /C:\"OS Version\"" },
    { label: "Network", cmd: "ipconfig | findstr IPv4" },
    { label: "Process List", cmd: "tasklist /FI \"STATUS eq running\"" },
    { label: "Disk Usage", cmd: "wmic logicaldisk get size,freespace,caption" },
  ];

  return (
    <div>
      <ConfirmDialog
        open={confirmOpen}
        title="Confirm Command Execution"
        message="This command requires your approval:"
        details={pendingCmd}
        onConfirm={handleConfirm}
        onDeny={handleDeny}
        onCancel={handleDeny}
      />
      <PageHeader icon="console" title="Console" subtitle="Run shell commands with safety gates" />
      <div className="row-wrap" style={{ marginBottom: 12, gap: 8 }}>
        {quickCommands.map((qc) => (
          <Button key={qc.label} size="sm" icon="zap" onClick={() => setInput(qc.cmd)}>{qc.label}</Button>
        ))}
      </div>
      <div className="console-output" ref={outRef as any}>
        {output.map((line, i) => (
          <div key={i} className={line.includes("⚠️") || line.includes("Error") ? "error" : ""}>
            {line || "\u00A0"}
          </div>
        ))}
      </div>
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <input
          className="input mono"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="> type a command..."
        />
        <Button variant="primary" icon="play" onClick={execute}>Run</Button>
        <Button icon="trash" onClick={() => setOutput(["Console cleared.", ""])}>Clear</Button>
      </div>
    </div>
  );
}
