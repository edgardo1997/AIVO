import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Reports } from "../components/Reports/Reports";
import { api, v1Api } from "../api";

vi.mock("../api", () => ({
  api: {
    sentinel: {
      reportPreview: vi.fn().mockResolvedValue({ provider: "openai", model: "gpt-4", selection_reason: "Best model", source_count: 5, source_chars: 10000, estimated_prompt_tokens: 2000, estimated_output_tokens: 500, estimated_total_tokens: 2500, estimated_cost_usd: 0.0125, sources: [], skipped_sensitive: [] }),
      exportReport: vi.fn().mockResolvedValue(new Blob(["report content"], { type: "text/markdown" })),
    },
  },
  v1Api: {
    execute: vi.fn().mockResolvedValue({ success: true, data: { report: "# Report\n\nContent here", provider: "openai", model: "gpt-4", sources: [{ path: "C:\\file.txt", name: "file.txt", chars: 1000 }], source_count: 1, source_chars: 1000, skipped_sensitive: [] }, requires_confirmation: false, action_id: null, duration_ms: 5000, error: null, pipeline: null }),
    confirm: vi.fn().mockResolvedValue({}),
  },
}));

const sentinel = api.sentinel;
const v1 = v1Api;

describe("Reports", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra formulario", async () => {
    render(<Reports />);
    expect(screen.getByPlaceholderText((v) => v.startsWith("C:") && v.includes("Users"))).toBeInTheDocument();
    expect(screen.getByDisplayValue(/Crear un informe ejecutivo/)).toBeInTheDocument();
    expect(screen.getByRole("slider")).toBeInTheDocument();
  });

  it("estima costo", async () => {
    render(<Reports />);
    const input = screen.getByPlaceholderText((v) => v.startsWith("C:") && v.includes("Users"));
    fireEvent.change(input, { target: { value: "C:\\test" } });

    fireEvent.click(screen.getByText("Estimar costo"));

    await waitFor(() => {
      expect(vi.mocked(sentinel.reportPreview)).toHaveBeenCalled();
    });
  });

  it("genera informe", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<Reports />);
    const input = screen.getByPlaceholderText((v) => v.startsWith("C:") && v.includes("Users"));
    fireEvent.change(input, { target: { value: "C:\\test" } });

    fireEvent.click(screen.getByText("Estimar costo"));
    await waitFor(() => {
      expect(screen.getByText("Generar informe")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Generar informe"));

    await waitFor(() => {
      expect(vi.mocked(v1.execute)).toHaveBeenCalled();
    });
    confirmSpy.mockRestore();
  });
});
