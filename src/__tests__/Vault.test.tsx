import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Vault } from "../components/Vault/Vault";

vi.mock("../api", () => ({
  api: {
    vault: {
      list: vi.fn().mockResolvedValue({ entries: [
        { id: "sec1", name: "My API Key", category: "api_key", value: "sk-1234567890abcdef", masked: true, rotatable: true, rotation_days: 90, last_rotated: null, notes: "For OpenAI", created_at: "2024-01-01", updated_at: "2024-01-01" },
      ] }),
      status: vi.fn().mockResolvedValue({ entry_count: 1, encryption_enabled: true, categories: ["api_key"] }),
      audit: vi.fn().mockResolvedValue({ audit: [] }),
      create: vi.fn().mockResolvedValue({}),
      delete: vi.fn().mockResolvedValue({}),
      reveal: vi.fn().mockResolvedValue({ value: "sk-1234567890abcdef" }),
      rotate: vi.fn().mockResolvedValue({}),
    },
  },
}));

import { api } from "../api";

describe("Vault", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra vault entries", async () => {
    render(<Vault />);
    expect(await screen.findByText("My API Key")).toBeInTheDocument();
  });

  it("muestra encryption status", async () => {
    render(<Vault />);
    expect(await screen.findByText("Encrypted at rest")).toBeInTheDocument();
  });

  it("reveal secret", async () => {
    render(<Vault />);
    await screen.findByText("My API Key");

    fireEvent.click(screen.getByText("Reveal"));

    await waitFor(() => {
      expect(api.vault.reveal).toHaveBeenCalledWith("sec1");
    });
  });

  it("abre create form", async () => {
    render(<Vault />);
    await screen.findByText("My API Key");

    fireEvent.click(screen.getByText("+ Add Secret"));

    expect(screen.getByPlaceholderText("ID *")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Name")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Secret value * (will be encrypted at rest)")).toBeInTheDocument();
  });
});
