import { render, screen, fireEvent } from "@testing-library/react";
import { Clarification } from "../components/Clarification/Clarification";
import { describe, it, expect, vi } from "vitest";

const sampleEvent = {
  clarification_id: "c1",
  correlation_id: "r1",
  question: "Which report do you mean?",
  response_language: "en",
  ambiguity_type: "entity",
  candidate_options: [
    { id: "a", label: "Downloads/report.pdf", meta: "modified today" },
    { id: "b", label: "Desktop/report.pdf", meta: "modified July 30" },
    { id: "c", label: "Documents/report.pdf", meta: "modified July 22" },
  ],
  allow_free_text: false,
  risk_if_wrong: "Wrong file could be deleted",
};

describe("Clarification", () => {
  it("renders the question and options", () => {
    render(<Clarification event={sampleEvent} onResolve={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByText("Which report do you mean?")).toBeInTheDocument();
    expect(screen.getByLabelText(/Downloads\/report\.pdf modified today/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Desktop\/report\.pdf modified July 30/)).toBeInTheDocument();
    expect(screen.getByText("Wrong file could be deleted")).toBeInTheDocument();
  });

  it("calls onResolve with selected option when confirmed", () => {
    const onResolve = vi.fn();
    const onCancel = vi.fn();
    render(<Clarification event={sampleEvent} onResolve={onResolve} onCancel={onCancel} />);
    fireEvent.click(screen.getByLabelText(/Downloads\/report\.pdf modified today/));
    fireEvent.click(screen.getByText("Confirm"));
    expect(onResolve).toHaveBeenCalledWith("c1", "a", undefined);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("calls onCancel when cancelled", () => {
    const onResolve = vi.fn();
    const onCancel = vi.fn();
    render(<Clarification event={sampleEvent} onResolve={onResolve} onCancel={onCancel} />);
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalledWith("c1");
    expect(onResolve).not.toHaveBeenCalled();
  });

  it("supports free-text answer when allowed", () => {
    const onResolve = vi.fn();
    render(<Clarification event={{ ...sampleEvent, allow_free_text: true }} onResolve={onResolve} onCancel={vi.fn()} />);
    const textarea = screen.getByLabelText("Free-text clarification");
    fireEvent.change(textarea, { target: { value: "the one from yesterday" } });
    fireEvent.click(screen.getByText("Confirm"));
    expect(onResolve).toHaveBeenCalledWith("c1", undefined, "the one from yesterday");
  });

  it("shows expired state when past expires_at", () => {
    const expired = { ...sampleEvent, expires_at: new Date(Date.now() - 1000).toISOString() };
    render(<Clarification event={expired} onResolve={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByText("This clarification has expired.")).toBeInTheDocument();
    expect(screen.getByText("Confirm")).toBeDisabled();
  });
});
