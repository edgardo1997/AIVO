import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { Chat } from "../components/Chat/Chat";

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

vi.mock("../api", () => ({
  api: {
    sentinel: {
      chat: vi.fn().mockResolvedValue({ response: "Your PC is running well. CPU at 45%, 8 GB of 16 GB RAM used." }),
    },
  },
}));

import { api } from "../api";

describe("Chat", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra mensaje inicial", async () => {
    render(<Chat />);
    expect(await screen.findByText(/Hi, I'm Sentinel/)).toBeInTheDocument();
  });

  it("muestra quick actions", async () => {
    render(<Chat />);
    expect(await screen.findByText("How's my PC doing?")).toBeInTheDocument();
    expect(screen.getByText("Show me my system specs")).toBeInTheDocument();
    expect(screen.getByText("What's using the most CPU?")).toBeInTheDocument();
    expect(screen.getByText("Clean up temporary files")).toBeInTheDocument();
    expect(screen.getByText("Open Task Manager")).toBeInTheDocument();
    expect(screen.getByText("List my top processes")).toBeInTheDocument();
  });

  it("envía mensaje", async () => {
    render(<Chat />);
    await screen.findByText(/Hi, I'm Sentinel/);

    fireEvent.change(screen.getByPlaceholderText("Ask anything about your PC..."), { target: { value: "How is my PC?" } });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() => {
      expect(api.sentinel.chat).toHaveBeenCalledWith("How is my PC?", expect.any(Array));
    });
    expect(await screen.findByText("Your PC is running well. CPU at 45%, 8 GB of 16 GB RAM used.")).toBeInTheDocument();
  });
});
