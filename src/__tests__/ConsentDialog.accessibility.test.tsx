import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConsentDialog } from "../components/ConsentDialog/ConsentDialog";

const pending = {
  id: "pending-1",
  tool_id: "executor.launch",
  risk_level: "medium",
  risk_label: "Medio",
  risk_description: "Se abrirá una aplicación conocida.",
  is_read_only: false,
  is_reversible: true,
  affected_resources: ["Bloc de notas"],
  estimated_impact: "Abrir Bloc de notas",
  simulation_summary: "No modifica archivos.",
  created_at: Date.now(),
  expires_at: Date.now() + 60_000,
  can_grant_permanent: false,
};

describe("ConsentDialog accesible", () => {
  it("Escape registra una cancelación real", async () => {
    const respond = vi.fn().mockResolvedValue(undefined);
    render(<ConsentDialog pending={pending} onRespond={respond} />);
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(respond).toHaveBeenCalledWith(false, "once"));
  });

  it("no ofrece permiso permanente cuando el backend no lo permite", () => {
    render(<ConsentDialog pending={pending} onRespond={() => {}} />);
    expect(screen.queryByRole("button", { name: "Permitir siempre" })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });
});
