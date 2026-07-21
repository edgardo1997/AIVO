import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { Chat } from "../components/Chat/Chat";

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

vi.mock("../api", () => ({
  api: {
    sentinel: {
      chat: vi.fn().mockResolvedValue({
        response: "Your PC is running well. CPU at 45%, 8 GB of 16 GB RAM used.",
        pipeline: {
          presentation: {
            version: 1,
            mode: "user",
            status: "completed",
            title: "Acción completada",
            summary: "Estado verificado del equipo.",
            risk: { level: "low", score: null },
            evidence: { required: 1, verified: 1, satisfied: true, sources: [] },
            next_action: null,
            details: null,
          },
        },
      }),
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
    expect(await screen.findByText(/Hola, soy Sentinel/)).toBeInTheDocument();
  });

  it("muestra quick actions", async () => {
    render(<Chat />);
    expect(await screen.findByText("¿Cómo está mi PC?")).toBeInTheDocument();
    expect(screen.getByText("Muéstrame las especificaciones")).toBeInTheDocument();
    expect(screen.getByText("¿Qué está usando más CPU?")).toBeInTheDocument();
    expect(screen.getByText("Limpia archivos temporales")).toBeInTheDocument();
    expect(screen.getByText("Abre el Administrador de Tareas")).toBeInTheDocument();
    expect(screen.getByText("Lista mis procesos principales")).toBeInTheDocument();
  });

  it("envía mensaje", async () => {
    render(<Chat />);
    await screen.findByText(/Hola, soy Sentinel/);

    fireEvent.change(screen.getByPlaceholderText("Pregunta cualquier cosa sobre tu PC..."), { target: { value: "How is my PC?" } });
    fireEvent.click(screen.getByText("Enviar"));

    await waitFor(() => {
      expect(api.sentinel.chat).toHaveBeenCalledWith("How is my PC?", expect.any(Array));
    });
    expect(await screen.findByText("Your PC is running well. CPU at 45%, 8 GB of 16 GB RAM used.")).toBeInTheDocument();
    expect(await screen.findByText(/1\/1 fuentes verificadas/)).toBeInTheDocument();
  });
});
