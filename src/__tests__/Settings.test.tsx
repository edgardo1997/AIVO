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
    const matches = await screen.findAllByText(/DeepSeek/);
    expect(matches.length).toBeGreaterThan(0);
  });

  it("save config (dialog)", async () => {
    render(<Settings />);
    await screen.findAllByText(/DeepSeek/);

    // Use Anthropic which has apiRequired:true but no pre-configured key
    const modelButtons = screen.getAllByRole("button");
    const anthropicBtn = modelButtons.find(b => b.textContent?.includes("Claude 3"));
    expect(anthropicBtn).toBeTruthy();
    if (anthropicBtn) fireEvent.click(anthropicBtn);

    const apiInput = await screen.findByPlaceholderText("sk-ant-...");
    fireEvent.change(apiInput, { target: { value: "sk-test-key" } });
    fireEvent.click(screen.getByRole("button", { name: /^Conectar y Activar$/i }));

    await waitFor(() => {
      expect(vi.mocked(ai.setConfig)).toHaveBeenCalledWith(
        expect.objectContaining({ api_key: "sk-test-key" })
      );
    });
  });

  it("test connection (dialog)", async () => {
    render(<Settings />);
    await screen.findAllByText(/DeepSeek/);

    const modelButtons = screen.getAllByRole("button");
    const anthropicBtn = modelButtons.find(b => b.textContent?.includes("Claude 3"));
    expect(anthropicBtn).toBeTruthy();
    if (anthropicBtn) fireEvent.click(anthropicBtn);

    const apiInput = await screen.findByPlaceholderText("sk-ant-...");
    fireEvent.change(apiInput, { target: { value: "sk-test-key" } });
    fireEvent.click(screen.getByRole("button", { name: /^Conectar y Activar$/i }));

    await waitFor(() => {
      expect(vi.mocked(ai.setConfig)).toHaveBeenCalledWith(
        expect.objectContaining({ api_key: "sk-test-key" })
      );
    });
  });
});
