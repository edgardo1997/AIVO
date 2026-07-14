import { render, screen, act } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppProvider, useAppState } from "../contexts/AppContext";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    permissions: { status: vi.fn().mockResolvedValue({ level: "auto", emergency_stop: false, pending_actions: 0 }) },
    monitor: { system: vi.fn().mockResolvedValue({}) },
  },
}));

function TestConsumer() {
  const { permissionLevel, emergencyStop, sidecarStatus, notifications, addNotification, removeNotification } = useAppState();
  return (
    <div>
      <span data-testid="level">{permissionLevel}</span>
      <span data-testid="emergency">{String(emergencyStop)}</span>
      <span data-testid="status">{sidecarStatus}</span>
      <span data-testid="notif-count">{notifications.length}</span>
      <button data-testid="add-info" onClick={() => addNotification({ type: "info", message: "info msg" })}>Add Info</button>
      <button data-testid="add-error" onClick={() => addNotification({ type: "error", message: "error msg" })}>Add Error</button>
      {notifications.map((n) => (
        <div key={n.id}>
          <span data-testid={`notif-${n.id}`}>{n.message}</span>
          <button data-testid={`remove-${n.id}`} onClick={() => removeNotification(n.id)}>Remove</button>
        </div>
      ))}
    </div>
  );
}

describe("AppContext", () => {
  it("actualiza permissionLevel vía API al montar", async () => {
    render(<AppProvider><TestConsumer /></AppProvider>);
    expect(await screen.findByText("auto")).toBeInTheDocument();
    expect(screen.getByTestId("emergency")).toHaveTextContent("false");
  });

  it("agrega y muestra notificaciones", async () => {
    render(<AppProvider><TestConsumer /></AppProvider>);
    await screen.findByText("auto");

    act(() => { screen.getByTestId("add-info").click(); });
    expect(screen.getByText("info msg")).toBeInTheDocument();

    act(() => { screen.getByTestId("add-error").click(); });
    expect(screen.getByText("error msg")).toBeInTheDocument();
    expect(screen.getByTestId("notif-count")).toHaveTextContent("2");
  });

  it("elimina notificaciones individuales", async () => {
    render(<AppProvider><TestConsumer /></AppProvider>);
    await screen.findByText("auto");

    act(() => { screen.getByTestId("add-info").click(); });
    expect(screen.getByText("info msg")).toBeInTheDocument();

    const removeBtn = screen.getByText("Remove");
    act(() => { removeBtn.click(); });
    expect(screen.queryByText("info msg")).not.toBeInTheDocument();
  });

  it("llama a permissions.status al montar", async () => {
    render(<AppProvider><TestConsumer /></AppProvider>);
    await screen.findByText("auto");
    expect(vi.mocked(api.permissions.status)).toHaveBeenCalled();
  });

  it("llama a monitor.system al montar", async () => {
    render(<AppProvider><TestConsumer /></AppProvider>);
    await screen.findByText("auto");
    expect(vi.mocked(api.monitor.system)).toHaveBeenCalled();
  });
});
