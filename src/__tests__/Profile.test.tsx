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
      presets: vi.fn().mockResolvedValue([
        { preset_name: "my-preset", description: "My preset", created_at: "2024-01-01T00:00:00Z" },
      ]),
      export: vi.fn().mockResolvedValue({}),
      import: vi.fn().mockResolvedValue({}),
      savePreset: vi.fn().mockResolvedValue({}),
      applyPreset: vi.fn().mockResolvedValue({}),
      deletePreset: vi.fn().mockResolvedValue({}),
      search: vi.fn().mockResolvedValue([
        { field: "theme", old_value: "light", new_value: "dark", changed_at: "2024-01-15T10:00:00Z" },
      ]),
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
    expect(screen.getByPlaceholderText("Search profile history...")).toBeInTheDocument();
  });

  it("realiza búsqueda", async () => {
    render(<Profile />);
    await screen.findByText("usr_123");

    const searchInput = screen.getByPlaceholderText("Search profile history...");
    fireEvent.change(searchInput, { target: { value: "theme" } });
    fireEvent.keyDown(searchInput, { key: "Enter" });

    await waitFor(() => {
      expect(screen.getByText(/theme/)).toBeInTheDocument();
    });
    expect(screen.getByText(/light/)).toBeInTheDocument();
    expect(screen.getByText(/dark/)).toBeInTheDocument();
  });
});
