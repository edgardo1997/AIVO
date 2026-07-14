import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Settings } from "../components/Settings/Settings";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    ai: {
      config: vi.fn().mockResolvedValue({ provider: "openrouter", api_key: "", base_url: "https://openrouter.ai/api/v1", model: "deepseek/deepseek-v4-flash:free", free_providers: { openrouter: { label: "OpenRouter", base_url: "https://openrouter.ai/api/v1", api_key_required: true, default_model: "deepseek/deepseek-v4-flash:free", description: "Free models", signup_url: "https://openrouter.ai" } } }),
      setConfig: vi.fn().mockResolvedValue({}),
      chat: vi.fn().mockResolvedValue({ response: "OK", model: "deepseek/deepseek-v4-flash:free" }),
    },
  },
}));

const ai = api.ai;

describe("Settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra AI Provider config", async () => {
    render(<Settings />);
    expect(await screen.findByText(/openrouter/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("deepseek/deepseek-v4-flash:free")).toBeInTheDocument();
  });

  it("save config", async () => {
    render(<Settings />);
    await screen.findByText(/openrouter/);

    fireEvent.click(screen.getByText("Save Config"));

    await waitFor(() => {
      expect(vi.mocked(ai.setConfig)).toHaveBeenCalled();
    });
  });

  it("test connection", async () => {
    render(<Settings />);
    await screen.findByText(/openrouter/);

    fireEvent.click(screen.getByText("Test Connection"));

    await waitFor(() => {
      expect(vi.mocked(ai.chat)).toHaveBeenCalled();
    });
  });
});
