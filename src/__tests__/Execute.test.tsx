import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Execute } from "../components/Execute/Execute";
import { v1Api } from "../api";

vi.mock("../api", () => ({
  v1Api: {
    execute: vi.fn().mockResolvedValue({ success: true, data: { stdout: "hello world\n", returncode: 0 }, requires_confirmation: false, action_id: null, duration_ms: 1500, error: null, pipeline: null }),
  },
}));

describe("Execute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders tool select and params editor", async () => {
    render(<Execute />);
    expect(screen.getByText("Tool ID")).toBeInTheDocument();
    expect(screen.getByText("Parameters (JSON)")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("ejecuta tool", async () => {
    render(<Execute />);

    fireEvent.click(screen.getByText("Execute"));

    await waitFor(() => {
      expect(v1Api.execute).toHaveBeenCalledWith("executor.command", { command: "echo hello" });
    });
  });
});
