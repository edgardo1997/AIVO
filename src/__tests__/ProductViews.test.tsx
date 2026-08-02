import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { product as productMock } from "../api/product";
import { ControlCenterView } from "../components/Product/ControlCenterView";
import { MetricsView } from "../components/Product/MetricsView";
import { ModelCenterView } from "../components/Product/ModelCenterView";
import { ModesView } from "../components/Product/ModesView";

vi.mock("../api/product", () => {
  const models = [
    {
      id: "gpt-4o", provider: "openai", display_name: "gpt-4o", local: false, kind: "cloud",
      status: "ready", cost: 0.005, speed: "fast", speed_label: "Alta", context_window: 128000,
      capabilities: ["tool_calling", "vision"], capability_labels: ["Herramientas", "Visión"],
      recommended_use: "Análisis", tags: ["reasoning"], favorite: false,
    },
    {
      id: "local-qwen", provider: "local", display_name: "local-qwen", local: true, kind: "local",
      status: "ready", cost: 0, speed: "medium", speed_label: "Media", context_window: 32000,
      capabilities: ["local", "coding"], capability_labels: ["Local", "Código"],
      recommended_use: "Código", tags: [], favorite: true,
    },
  ];

  const overview = {
    resources: {
      available: true,
      cpu: { percent: 45.5 },
      memory: { percent: 62.3, used_gb: 8.1, total_gb: 16.0 },
      disk: { percent: 50.0, free_gb: 100.0 },
      gpu: { available: false, percent: null, note: "GPU no reportada" },
      processes: 220,
      uptime: 3600,
    },
    processes: [
      { pid: 1, name: "chrome", memory_percent: 5.2, cpu_percent: 1.1, safe_to_close: false },
      { pid: 2, name: "msedgewebview2.exe", memory_percent: 8.0, cpu_percent: 0.5, safe_to_close: true },
    ],
    applications: [{ name: "VS Code", path: "code" }],
    network: { available: true, connected: true, connections: 12 },
    recommendations: [
      { severity: "ok", title: "Sistema en buen estado", detail: "Sin presión crítica de recursos.", action: null },
    ],
    timestamp: 0,
  };

  return {
    product: {
      listModes: vi.fn().mockResolvedValue([
        { id: "developer", name: "Developer Mode", short: "Desarrollador", icon: "</>", description: "Optimiza Sentinel para programar.", capabilities: ["VS Code", "Git"], model_priority: "coding", power: "balanced", primary_color: "#4f8cff", active: false },
        { id: "gaming", name: "Gaming Mode", short: "Juego", icon: "▶", description: "Libera recursos para tus juegos.", capabilities: ["Detectar juego"], model_priority: "fast", power: "ultimate", primary_color: "#ff5d73", active: true },
      ]),
      modesStatus: vi.fn().mockResolvedValue({
        active_mode: "gaming",
        active: null,
        last_actions: ["power_plan=ultimate"],
        history: [{ mode_id: "developer", model_priority: "coding", power: "balanced", ts: 1000 }],
        rollback_available: true,
        model_priority: "fast",
      }),
      recommendMode: vi.fn().mockResolvedValue({ recommended: null, context: {} }),
      activateMode: vi.fn().mockResolvedValue({ success: true, mode_id: "developer", previous: null, actions: [] }),
      deactivateMode: vi.fn().mockResolvedValue({ success: true, mode_id: null, previous: "gaming", actions: [] }),
      rollbackMode: vi.fn().mockResolvedValue({ success: true, mode_id: "developer", actions: [] }),
      modelCenter: vi.fn().mockResolvedValue({
        models, favorites: ["local-qwen"], priority: "balanced",
        priority_label: "Equilibrado", count: models.length,
      }),
      setFavorite: vi.fn().mockResolvedValue({ success: true }),
      setPriority: vi.fn().mockResolvedValue({ success: true }),
      metrics: vi.fn().mockResolvedValue({
        span_days: 14,
        time_to_first_action: { recorded: 3, avg_ms: 4500 },
        actions_completed: 42,
        automations_created: 5,
        ux_errors: 2,
        success_rate: 0.95,
        usage_by_mode: { developer: 10, gaming: 3 },
        sessions: 12,
        retention: {
          active_days: 9,
          ratio: 0.643,
          daily: [
            { day: "2026-07-30", actions: 12, sessions: 4, errors: 1 },
            { day: "2026-07-31", actions: 30, sessions: 8, errors: 1 },
          ],
        },
      }),
      recordEvent: vi.fn().mockResolvedValue({ success: true, event_type: "x" }),
      controlCenter: vi.fn().mockResolvedValue(overview),
      optimize: vi.fn().mockResolvedValue({ success: true, mode: "balanced", dry_run: true, actions: ["cleanup"], errors: [], context: {}, snapshot_id: "s1" }),
      freeResources: vi.fn().mockResolvedValue({
        success: true, commit: false, preview: true,
        candidates: [{ pid: 2, name: "msedgewebview2.exe", memory_percent: 8.0, safe: true }],
        terminated: [],
        note: "Solo se cierran procesos seguros.",
      }),
      createProfile: vi.fn().mockResolvedValue({ success: true, profile_id: "profile-1", name: "profile", created_at: 0 }),
    },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ModesView", () => {
  it("renderiza los modos disponibles", async () => {
    render(<ModesView />);
    expect(await screen.findByText("Developer Mode")).toBeInTheDocument();
    expect(screen.getAllByText("Gaming Mode").length).toBeGreaterThan(0);
  });

  it("muestra el modo activo y el historial", async () => {
    render(<ModesView />);
    expect(await screen.findByText("Activo", { selector: ".sntl-badge" })).toBeInTheDocument();
    expect(screen.getByText("developer", { selector: ".sntl-timeline-title" })).toBeInTheDocument();
  });

  it("abre el diálogo al pulsar un modo inactivo y activa", async () => {
    render(<ModesView />);
    fireEvent.click(await screen.findByText("Developer Mode"));
    expect(await screen.findByText("Activar Developer Mode")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Activar", { selector: ".sntl-btn--primary" }));
    await waitFor(() => expect(vi.mocked(productMock.activateMode)).toHaveBeenCalledWith("developer", ""));
  });
});

describe("ModelCenterView", () => {
  it("muestra modelos locales y en la nube", async () => {
    render(<ModelCenterView />);
    expect(await screen.findByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("local-qwen")).toBeInTheDocument();
  });

  it("muestra prioridad seleccionada y favorito", async () => {
    render(<ModelCenterView />);
    expect(await screen.findByText("prioridad: Equilibrado")).toBeInTheDocument();
    expect(screen.getByText("★")).toBeInTheDocument();
  });

  it("alterna favorito", async () => {
    render(<ModelCenterView />);
    const stars = await screen.findAllByRole("button", { name: "Quitar de favoritos" });
    fireEvent.click(stars[0]);
    await waitFor(() => expect(vi.mocked(productMock.setFavorite)).toHaveBeenCalledWith("local-qwen", false));
  });
});

describe("MetricsView", () => {
  it("muestra KPIs de producto", async () => {
    render(<MetricsView />);
    expect(await screen.findByText("42")).toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("4.5s")).toBeInTheDocument();
  });

  it("muestra uso por modo y actividad diaria", async () => {
    render(<MetricsView />);
    expect(await screen.findByText("developer")).toBeInTheDocument();
    expect(screen.getByText("gaming")).toBeInTheDocument();
    expect(screen.getByText("07-30")).toBeInTheDocument();
  });
});

describe("ControlCenterView", () => {
  it("muestra recursos y procesos", async () => {
    render(<ControlCenterView />);
    expect(await screen.findByText("46%")).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(screen.getByText("chrome")).toBeInTheDocument();
    expect(screen.getByText("msedgewebview2.exe")).toBeInTheDocument();
  });

  it("muestra recomendaciones", async () => {
    render(<ControlCenterView />);
    expect(await screen.findByText("Sistema en buen estado")).toBeInTheDocument();
  });

  it("abre vista previa de liberar RAM", async () => {
    render(<ControlCenterView />);
    fireEvent.click(await screen.findByText("Liberar RAM"));
    await waitFor(() => expect(vi.mocked(productMock.freeResources)).toHaveBeenCalledWith(false));
    expect(await screen.findByText(/Solo se cierran procesos seguros/)).toBeInTheDocument();
  });
});
