import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Profile } from "../components/Profile/Profile";

vi.mock("../api", () => ({
  api: {
    profile: {
      get: vi.fn().mockResolvedValue({
        identity: { user_id: "usr_123", username: "jdoe", role: "admin", is_local: true },
        profile: { user_id: "usr_123", username: "jdoe", display_name: "John Doe", theme: "dark", timezone: "UTC", locale: "en" },
        preferences: { language: "en", notifications: true },
      }),
      update: vi.fn().mockResolvedValue({}),
      setPreference: vi.fn().mockResolvedValue({}),
      deletePreference: vi.fn().mockResolvedValue({}),
      presets: vi.fn().mockResolvedValue({ presets: [
        { preset_name: "my-preset", description: "My preset", created_at: "2024-01-01T00:00:00Z" },
      ], count: 1 }),
      export: vi.fn().mockResolvedValue({}),
      import: vi.fn().mockResolvedValue({}),
      savePreset: vi.fn().mockResolvedValue({}),
      applyPreset: vi.fn().mockResolvedValue({}),
      deletePreset: vi.fn().mockResolvedValue({}),
      search: vi.fn().mockResolvedValue({ results: [
        { user_id: "usr_123", username: "jdoe", display_name: "John Doe", avatar: "", theme: "dark", bio: "Test profile", tags: ["theme"] },
      ], count: 1 }),
    },
  },
}));

describe("Profile", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra identity y profile", async () => {
    render(<Profile />);
    expect(await screen.findByText("usr_123")).toBeInTheDocument();
    expect(screen.getByDisplayValue("John Doe")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveValue("dark");
  });

  it("muestra presets", async () => {
    render(<Profile />);
    expect(await screen.findByText("my-preset")).toBeInTheDocument();
    expect(screen.getByText("My preset")).toBeInTheDocument();
  });

  it("agrega preferencia", async () => {
    render(<Profile />);
    await screen.findByText("usr_123");

    fireEvent.change(screen.getByPlaceholderText("Key"), { target: { value: "language" } });
    fireEvent.change(screen.getByPlaceholderText("Value"), { target: { value: "es" } });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(screen.getByText(/language/)).toBeInTheDocument();
    });
  });

  it("muestra History Search section", async () => {
    render(<Profile />);
    await screen.findByText("usr_123");
    expect(screen.getByPlaceholderText("Search profiles...")).toBeInTheDocument();
  });

  it("realiza búsqueda", async () => {
    render(<Profile />);
    await screen.findByText("usr_123");

    const searchInput = screen.getByPlaceholderText("Search profiles...");
    fireEvent.change(searchInput, { target: { value: "theme" } });
    fireEvent.keyDown(searchInput, { key: "Enter" });

    await waitFor(() => {
      expect(screen.getByText(/John Doe/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Test profile/)).toBeInTheDocument();
  });
});
