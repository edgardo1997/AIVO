import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Files } from "../components/Files/Files";

vi.mock("../api", () => ({
  v1Api: {
    execute: vi.fn().mockImplementation(async (toolId: string, _params: any) => {
      if (toolId === "filesystem.list") {
        return { success: true, data: { path: "C:\\", entries: [
          { name: "Users", path: "C:\\Users", is_dir: true, size: 0 },
          { name: "file.txt", path: "C:\\file.txt", is_dir: false, size: 1024 },
        ] }, requires_confirmation: false, action_id: null, duration_ms: 100, error: null, pipeline: null };
      }
      if (toolId === "filesystem.search") {
        return { success: true, data: { results: ["C:\\file.txt", "C:\\docs\\file2.txt"] }, requires_confirmation: false, action_id: null, duration_ms: 50, error: null, pipeline: null };
      }
      return { success: true, data: {}, requires_confirmation: false, action_id: null, duration_ms: null, error: null, pipeline: null };
    }),
  },
}));

import { v1Api } from "../api";

describe("Files", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra file browser", async () => {
    render(<Files />);
    fireEvent.click(screen.getByText("Browse"));
    expect(await screen.findByText(/Users/)).toBeInTheDocument();
    expect(screen.getByText(/file\.txt/)).toBeInTheDocument();
  });

  it("navega a directorio", async () => {
    render(<Files />);
    fireEvent.click(screen.getByText("Browse"));
    await screen.findByText(/Users/);

    fireEvent.click(screen.getByText(/Users/));

    await waitFor(() => {
      expect(v1Api.execute).toHaveBeenCalledWith("filesystem.list", { path: "C:\\Users" });
    });
  });

  it("busca archivos", async () => {
    render(<Files />);
    fireEvent.click(screen.getByText("Browse"));
    await screen.findByText(/Users/);

    fireEvent.change(screen.getByPlaceholderText("Search files..."), { target: { value: "test query" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => {
      expect(v1Api.execute).toHaveBeenCalledWith("filesystem.search", { query: "test query" });
    });
    expect(await screen.findByText("C:\\file.txt")).toBeInTheDocument();
    expect(screen.getByText("C:\\docs\\file2.txt")).toBeInTheDocument();
  });
});
