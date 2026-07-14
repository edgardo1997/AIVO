import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Monitor } from "../components/Monitor/Monitor";

vi.mock("../api", () => ({
  api: {
    monitor: {
      cpu: vi.fn().mockResolvedValue({ percent: 45, count: 8, freq: { current: 2500 } }),
      memory: vi.fn().mockResolvedValue({ percent: 62, total: 17179869184, used: 10651518894, swap_percent: 10, swap_used: 1000000000, swap_total: 10000000000 }),
      disk: vi.fn().mockResolvedValue({ partitions: [{ mountpoint: "C:\\", fstype: "NTFS", total: 500000000000, used: 300000000000, free: 200000000000, percent: 60 }] }),
      network: vi.fn().mockResolvedValue({ bytes_recv: 1024000, bytes_sent: 512000, connections: [{}, {}, {}] }),
      processes: vi.fn().mockResolvedValue([
        { pid: 1, name: "systemd", cpu_percent: 0.5, memory_percent: 1.2, status: "running" },
        { pid: 2, name: "chrome", cpu_percent: 12.3, memory_percent: 8.1, status: "running" },
      ]),
    },
  },
  v1Api: {
    execute: vi.fn().mockResolvedValue({ success: true, data: {}, requires_confirmation: false, action_id: null, duration_ms: null, error: null, pipeline: null }),
  },
}));

describe("Monitor", () => {
  it("renders system metrics", async () => {
    render(<Monitor />);
    expect(await screen.findByText("45.0%")).toBeInTheDocument();
    expect(screen.getByText("62.0%")).toBeInTheDocument();
    expect(screen.getByText("10.0%")).toBeInTheDocument();
  });

  it("muestra tabla de procesos", async () => {
    render(<Monitor />);
    expect(await screen.findByText("systemd")).toBeInTheDocument();
    expect(screen.getByText("chrome")).toBeInTheDocument();
    expect(screen.getByText("PID")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("CPU%")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("muestra Network section", async () => {
    render(<Monitor />);
    expect(await screen.findByText(/received/)).toBeInTheDocument();
    expect(screen.getByText(/sent/)).toBeInTheDocument();
  });
});
