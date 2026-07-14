import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Policies } from "../components/Policies/Policies";

vi.mock("../api", () => ({
  v1Api: {
    listPolicies: vi.fn().mockResolvedValue([
      { id: "security", description: "Security rules", source: "security.yaml" },
      { id: "destructive", description: "Destructive patterns", source: "destructive_patterns.yaml" },
    ]),
    reloadPolicies: vi.fn().mockResolvedValue({ status: "reloaded" }),
  },
}));

describe("Policies", () => {
  it("lista policies al montar", async () => {
    render(<Policies />);
    expect(await screen.findByText("security")).toBeInTheDocument();
    expect(screen.getByText("destructive")).toBeInTheDocument();
    expect(screen.getByText("Security rules")).toBeInTheDocument();
    expect(screen.getByText("Destructive patterns")).toBeInTheDocument();
  });

  it("recarga policies", async () => {
    render(<Policies />);
    expect(await screen.findByText("security")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Reload from YAML"));
    expect(await screen.findByText("Reloaded: reloaded")).toBeInTheDocument();
  });
});
