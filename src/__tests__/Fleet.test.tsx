import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Fleet } from "../components/Fleet/Fleet";

vi.mock("../api", () => ({
  api: {
    fleet: {
      status: vi.fn().mockResolvedValue({ local_ip: "192.168.1.10", api_port: 8080, api_url: "http://192.168.1.10:8080", remote_enabled: true, paired: false }),
      generatePairing: vi.fn().mockResolvedValue({ token: "ABC123" }),
      qr: vi.fn().mockResolvedValue({ qr_data: "qrstring" }),
      revokePairing: vi.fn().mockResolvedValue({}),
      toggleRemote: vi.fn().mockResolvedValue({}),
    },
  },
}));

describe("Fleet", () => {
  it("muestra Connection Info", async () => {
    render(<Fleet />);
    expect(await screen.findByText("192.168.1.10")).toBeInTheDocument();
    expect(screen.getByText("8080")).toBeInTheDocument();
    expect(screen.getAllByText("http://192.168.1.10:8080").length).toBeGreaterThanOrEqual(1);
  });

  it("muestra Remote enabled", async () => {
    render(<Fleet />);
    expect(await screen.findByText("Enabled")).toBeInTheDocument();
  });

  it("generate pairing token", async () => {
    render(<Fleet />);
    expect(await screen.findByText("Generate Pairing Token")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Generate Pairing Token"));
    expect(await screen.findByText("ABC123")).toBeInTheDocument();
    expect(screen.getByText("qrstring")).toBeInTheDocument();
  });
});
