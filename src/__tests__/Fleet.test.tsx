import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppProvider } from "../contexts/AppContext";
import { Fleet } from "../components/Fleet/Fleet";

const mockApi = vi.hoisted(() => ({
  fleet: {
    status: vi.fn().mockResolvedValue({ local_ip: "192.168.1.10", api_port: 8080, api_url: "http://192.168.1.10:8080", remote_enabled: true, paired: false, device_count: 1 }),
    generatePairing: vi.fn().mockResolvedValue({ token: "ABC123" }),
    qr: vi.fn().mockResolvedValue({ qr_data: "qrstring" }),
    revokePairing: vi.fn().mockResolvedValue({}),
    toggleRemote: vi.fn().mockResolvedValue({}),
    listDevices: vi.fn().mockResolvedValue({ devices: [] }),
    getDevice: vi.fn(),
    registerDevice: vi.fn(),
    updateDevice: vi.fn(),
    deleteDevice: vi.fn(),
    syncPush: vi.fn(),
    syncPull: vi.fn(),
    syncLog: vi.fn().mockResolvedValue({ logs: [] }),
  },
  permissions: { status: vi.fn().mockResolvedValue({ level: "auto", emergency_stop: false, pending_actions: 0 }), rules: vi.fn().mockResolvedValue({ rules: [] }), setLevel: vi.fn(), emergency: vi.fn(), addRule: vi.fn(), deleteRule: vi.fn() },
  monitor: { system: vi.fn().mockResolvedValue({}) },
}));

vi.mock("../api", () => ({ api: mockApi }));

describe("Fleet", () => {
  it("shows Connection Info in Overview tab", async () => {
    render(<AppProvider><Fleet /></AppProvider>);
    expect(await screen.findByText("192.168.1.10")).toBeInTheDocument();
    expect(screen.getByText("8080")).toBeInTheDocument();
    expect(screen.getAllByText("http://192.168.1.10:8080").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("shows Remote enabled", async () => {
    render(<AppProvider><Fleet /></AppProvider>);
    expect(await screen.findByText("Enabled")).toBeInTheDocument();
  });

  it("generate pairing token", async () => {
    render(<AppProvider><Fleet /></AppProvider>);
    expect(await screen.findByText("Generate Pairing Token")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Generate Pairing Token"));
    expect(await screen.findByText("ABC123")).toBeInTheDocument();
    expect(screen.getByText("qrstring")).toBeInTheDocument();
  });

  it("switches between tabs", async () => {
    render(<AppProvider><Fleet /></AppProvider>);
    expect(await screen.findByText("Overview")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Devices"));
    expect(await screen.findByText("Register Device")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Sync"));
    expect(await screen.findByText("Sync with Peer")).toBeInTheDocument();
  });
});
