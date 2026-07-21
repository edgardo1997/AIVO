import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Dashboard } from "../components/Dashboard/Dashboard";

vi.mock("../api", () => ({
  api: {
    monitor: {
      cpu: vi.fn().mockResolvedValue({ percent: 45, count: 8, freq: { current: 2500 } }),
      memory: vi.fn().mockResolvedValue({ percent: 62, total: 17179869184, used: 10651518894, swap_percent: 10, swap_used: 1000000000, swap_total: 10000000000 }),
      disk: vi.fn().mockResolvedValue({ partitions: [{ mountpoint: "C:\\", fstype: "NTFS", total: 500000000000, used: 300000000000, free: 200000000000, percent: 60 }] }),
    },
    ai: {
      analyze: vi.fn().mockResolvedValue({ analysis: "System is healthy" }),
    },
  },
}));

describe("Dashboard", () => {
  it("renders CPU, RAM, Disk metrics", async () => {
    render(<Dashboard />);
    expect(await screen.findByText("45.0%")).toBeInTheDocument();
    expect(screen.getByText("62.0%")).toBeInTheDocument();
    expect(screen.getByText("60.0%")).toBeInTheDocument();
  });

  it("muestra AI Analysis section", async () => {
    render(<Dashboard />);
    expect(await screen.findByText("Análisis Inteligente")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Analizar"));
    expect(await screen.findByText("System is healthy")).toBeInTheDocument();
  });
});
