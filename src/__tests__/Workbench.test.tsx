import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Workbench } from "../components/Workbench/Workbench";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    permissions: {
      status: vi.fn().mockResolvedValue({ level: "confirm", emergency_stop: false, pending_actions: 0 }),
      setLevel: vi.fn(),
      emergency: vi.fn(),
    },
    ai: {
      config: vi.fn().mockResolvedValue({
        provider: "sentinel_local",
        model: "Qwen3-1.7B-Q8_0.gguf",
        strategy: "priority",
        preferred_provider: "sentinel_local",
        free_providers: {
          sentinel_local: { label: "Sentinel Local", base_url: "http://127.0.0.1:11435/v1", default_model: "Qwen3-1.7B-Q8_0.gguf", api_key_required: false },
          ollama: { label: "Ollama", base_url: "http://localhost:11434/v1", default_model: "llama3", api_key_required: false },
        },
      }),
      setConfig: vi.fn().mockResolvedValue({ status: "saved" }),
    },
    sentinel: {
      conversationCapabilities: vi.fn().mockResolvedValue({
        models: { available: true, available_count: 1, providers: ["sentinel_local"] },
        system: { registered_count: 58, categories: ["system"] },
      }),
      chat: vi.fn(),
      streamChat: vi.fn(),
      approve: vi.fn(),
      reject: vi.fn(),
      conversations: vi.fn().mockResolvedValue({ conversations: [] }),
      saveConversation: vi.fn().mockResolvedValue({}),
      deleteConversation: vi.fn().mockResolvedValue({ deleted: true }),
    },
  },
  v1Api: { listAudit: vi.fn().mockResolvedValue({ entries: [] }) },
}));

const storageKey = "sentinel.workbench.conversations.v1";

describe("Workbench", () => {
  beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); });

  it("recupera conversaciones guardadas y conserva el compositor", async () => {
    localStorage.setItem(storageKey, JSON.stringify([{
      id: "saved-session",
      title: "Aprender Python",
      updatedAt: 1,
      messages: [{ id: "message-1", prompt: "Enséñame Python", response: "Primera lección" }],
    }]));

    render(<Workbench />);

    expect(await screen.findByText("Aprender Python")).toBeInTheDocument();
    expect(screen.getAllByText("Enséñame Python").length).toBeGreaterThan(0);
    expect(screen.getByText("Primera lección")).toBeInTheDocument();
    expect(screen.getByLabelText("Solicitud para Sentinel")).toBeInTheDocument();
  });

  it("crea otra conversación sin borrar la anterior", async () => {
    localStorage.setItem(storageKey, JSON.stringify([{
      id: "saved-session",
      title: "Conversación anterior",
      updatedAt: 1,
      messages: [{ id: "message-1", prompt: "Mensaje anterior", response: "Respuesta anterior" }],
    }]));

    render(<Workbench />);
    fireEvent.click(await screen.findByText("Nueva misión"));

    expect(screen.getByText("Conversación anterior")).toBeInTheDocument();
    expect(screen.getByText("¿Qué quieres conseguir?")).toBeInTheDocument();
    await waitFor(() => expect(JSON.parse(localStorage.getItem(storageKey) || "[]")).toHaveLength(2));
  });

  it("reintenta un mensaje fallido sin incluirlo en el contexto", async () => {
    localStorage.setItem(storageKey, JSON.stringify([{
      id: "failed-session",
      title: "Intento fallido",
      updatedAt: 1,
      messages: [{
        id: "message-failed",
        prompt: "Explícame una lista",
        error: "El proveedor tardó demasiado en responder.",
        errorCode: "provider_timeout",
        retryable: true,
      }],
    }]));
    vi.mocked(api.sentinel.streamChat).mockResolvedValueOnce(undefined);

    render(<Workbench />);
    fireEvent.click(await screen.findByRole("button", { name: "Reintentar" }));

    await waitFor(() => expect(api.sentinel.streamChat).toHaveBeenCalled());
    expect(vi.mocked(api.sentinel.streamChat).mock.calls[0][0]).toBe("Explícame una lista");
    expect(vi.mocked(api.sentinel.streamChat).mock.calls[0][1]).toEqual([]);
  });

  it("cancela una generación activa y conserva el resultado parcial", async () => {
    vi.mocked(api.sentinel.streamChat).mockImplementationOnce(async (_message, _context, _session, onEvent, signal) => {
      onEvent({ type: "delta", text: "Resultado parcial" });
      await new Promise<void>((resolve) => signal?.addEventListener("abort", () => resolve(), { once: true }));
    });
    render(<Workbench />);
    const composer = screen.getByLabelText("Solicitud para Sentinel");
    fireEvent.change(composer, { target: { value: "Genera una explicación larga" } });
    fireEvent.click(screen.getByLabelText("Enviar solicitud"));

    fireEvent.click(await screen.findByRole("button", { name: "Detener" }));

    expect(await screen.findByText("Resultado parcial")).toBeInTheDocument();
    expect(screen.getByText("Generación cancelada por el usuario.")).toBeInTheDocument();
    expect(screen.getByText("Diagnóstico: user_cancelled")).toBeInTheDocument();
  });

  it("agrupa deltas visuales y persiste la conversación únicamente al terminar", async () => {
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => {
      frames.push(callback);
      return frames.length;
    }));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    let finishStream = () => {};
    const streamFinished = new Promise<void>((resolve) => { finishStream = resolve; });
    let streamStarted = () => {};
    const started = new Promise<void>((resolve) => { streamStarted = resolve; });
    vi.mocked(api.sentinel.streamChat).mockImplementationOnce(async (_message, _context, _session, onEvent) => {
      onEvent({ type: "delta", text: "Uno " });
      onEvent({ type: "delta", text: "dos " });
      onEvent({ type: "delta", text: "tres" });
      streamStarted();
      await streamFinished;
      onEvent({ type: "done" });
    });

    render(<Workbench />);
    await waitFor(() => expect(localStorage.getItem(storageKey)).not.toBeNull());
    vi.mocked(api.sentinel.saveConversation).mockClear();
    const storageWrite = vi.spyOn(Storage.prototype, "setItem");
    const composer = screen.getByLabelText("Solicitud para Sentinel");
    fireEvent.change(composer, { target: { value: "Respuesta progresiva" } });
    fireEvent.click(screen.getByLabelText("Enviar solicitud"));
    await started;

    expect(frames).toHaveLength(1);
    expect(storageWrite).not.toHaveBeenCalled();
    act(() => frames[0](performance.now()));
    expect(await screen.findByText("Uno dos tres")).toBeInTheDocument();
    expect(storageWrite).not.toHaveBeenCalled();

    await act(async () => { finishStream(); await streamFinished; });
    await waitFor(() => expect(storageWrite).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.sentinel.saveConversation).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.sentinel.saveConversation).mock.calls[0][1].messages.at(-1)?.response).toBe("Uno dos tres");
    storageWrite.mockRestore();
    vi.unstubAllGlobals();
  });

  it("mantiene la interfaz operativa cuando el almacenamiento local rechaza la escritura", async () => {
    const quotaError = new Error("Quota exceeded");
    quotaError.name = "QuotaExceededError";
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation((key) => {
      if (key === "sentinel.workbench.conversations.v1") throw quotaError;
    });

    render(<Workbench />);

    expect(await screen.findByText(/el almacenamiento local está lleno o no está disponible/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Solicitud para Sentinel")).toBeInTheDocument();
    storageWrite.mockRestore();
  });

  it("mantiene la conversación disponible durante el paro de herramientas", async () => {
    const quotaError = new Error("Quota exceeded");
    quotaError.name = "QuotaExceededError";
    vi.spyOn(Storage.prototype, "setItem").mockImplementation((key) => {
      if (key === "sentinel.workbench.conversations.v1") throw quotaError;
    });
    vi.mocked(api.permissions.status).mockResolvedValue({
      level: "confirm",
      emergency_stop: true,
      pending_actions: 0,
    } as never);

    render(<Workbench />);

    const composer = await screen.findByLabelText("Solicitud para Sentinel");
    await waitFor(() => expect(composer).not.toBeDisabled());
    expect(composer).toHaveAttribute(
      "placeholder",
      "Puedes seguir conversando; las acciones del equipo están detenidas",
    );
  });
});
