import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { Agents } from "../components/Agents/Agents";
import { api } from "../api";

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

vi.mock("../api", () => ({
  api: {
    agents: {
      list: vi.fn().mockResolvedValue([
        { id: "agent1", name: "Agent One", description: "Does things", provider: "ollama", model: "llama3", capabilities: ["code", "analyze"], allowed_tools: ["executor.*"], system_prompt: "You are an agent", status: "active", max_concurrency: 1 },
      ]),
      create: vi.fn().mockResolvedValue({}),
      delete: vi.fn().mockResolvedValue({}),
      update: vi.fn().mockResolvedValue({}),
    },
    sentinel: {
      multiAgent: vi.fn().mockResolvedValue({ success: true, sub_task_results: [{ sub_task_id: "task1", success: true, duration_ms: 1000 }] }),
    },
  },
}));

describe("Agents", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra agents list", async () => {
    render(<Agents />);
    expect(await screen.findByText("Agent One")).toBeInTheDocument();
  });

  it("cambia a chat tab", async () => {
    render(<Agents />);
    await screen.findByText("Agent One");

    fireEvent.click(screen.getByText("Multi-Agent Chat"));
    expect(await screen.findByPlaceholderText(/Describe a task/)).toBeInTheDocument();
  });

  it("abre create form", async () => {
    render(<Agents />);
    await screen.findByText("Agent One");

    fireEvent.click(screen.getByText("+ New Agent"));
    expect(await screen.findByPlaceholderText("ID *")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Name")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Description")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Model/)).toBeInTheDocument();
    expect(screen.getByText("Create")).toBeInTheDocument();
    expect(screen.getByText("Create Agent")).toBeInTheDocument();
  });
});
