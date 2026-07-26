import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TrustFlow } from "../components/TrustFlow/TrustFlow";

const pipeline = {
  blocked: true,
  action_id: "action-1",
  intent: { action: "launch", target: "executor.launch", parameters: { name: "Bloc de notas" } },
  plan: { steps: [{ description: "Resolver la aplicación instalada" }, { description: "Solicitar apertura" }] },
  decision: { final_risk_score: 0.2, policy_ids: ["application.launch.known"] },
  simulation_summary: "Abrirá una aplicación conocida.",
};

describe("TrustFlow", () => {
  it("explica intención, recurso, riesgo, plan y política en lenguaje visible", () => {
    render(<TrustFlow pipeline={pipeline} expanded onToggle={() => {}} />);
    expect(screen.getByText("abrir una aplicación")).toBeInTheDocument();
    expect(screen.getByText("Bloc de notas")).toBeInTheDocument();
    expect(screen.getByText("Bajo")).toBeInTheDocument();
    expect(screen.getByText("Resolver la aplicación instalada")).toBeInTheDocument();
    expect(screen.getByText("application.launch.known")).toBeInTheDocument();
    expect(screen.getByText("Nada se ejecutará hasta que decidas.")).toBeInTheDocument();
  });

  it("expone decisiones reales mediante botones y estado accesible", () => {
    const review = vi.fn();
    const reject = vi.fn();
    render(
      <TrustFlow
        pipeline={pipeline}
        expanded={false}
        onToggle={() => {}}
        onReviewConsent={review}
        onReject={reject}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancelar acción" }));
    fireEvent.click(screen.getByRole("button", { name: "Revisar y decidir" }));
    expect(reject).toHaveBeenCalledOnce();
    expect(review).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("Requiere consentimiento");
  });

  it("explica un fallo y conserva estado seguro", () => {
    render(
      <TrustFlow
        pipeline={{ ...pipeline, blocked: false, tool_result: { success: false, error: "Aplicación no encontrada" } }}
        expanded
        onToggle={() => {}}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Falló sin continuar");
    expect(screen.getByText(/Aplicación no encontrada/)).toBeInTheDocument();
  });
});
