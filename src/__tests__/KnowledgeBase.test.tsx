import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { KnowledgeBase } from "../components/KnowledgeBase/KnowledgeBase";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    knowledge: {
      list: vi.fn(),
      stats: vi.fn(),
      search: vi.fn(),
      addText: vi.fn(),
      addFile: vi.fn(),
      delete: vi.fn(),
      clear: vi.fn(),
      rebuild: vi.fn(),
    },
  },
}));

const kb = api.knowledge;

const mockDocs = {
  documents: [
    { doc_id: "doc1", source: "notes.txt", chunks: 3, created_at: "2026-07-14T10:00:00Z" },
    { doc_id: "doc2", source: "manual.pdf", chunks: 15, created_at: "2026-07-13T10:00:00Z" },
  ],
  total: 2,
};

const mockStats = {
  enabled: true, documents: 2, chunks: 18,
  embedding_provider: "openai", chunk_size: 512, chunk_overlap: 64,
};

describe("KnowledgeBase", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(kb.list).mockResolvedValue(mockDocs);
    vi.mocked(kb.stats).mockResolvedValue(mockStats);
  });

  it("muestra documentos de la API", async () => {
    render(<KnowledgeBase />);
    expect(await screen.findByText("notes.txt")).toBeInTheDocument();
    expect(screen.getByText("manual.pdf")).toBeInTheDocument();
  });

  it("muestra estadísticas", async () => {
    render(<KnowledgeBase />);
    expect(await screen.findByText(/openai/)).toBeInTheDocument();
    expect(screen.getAllByText(/18 chunks/).length).toBeGreaterThanOrEqual(1);
  });

  it("abre el formulario Add Text", async () => {
    render(<KnowledgeBase />);
    await screen.findByText("notes.txt");

    fireEvent.click(screen.getByText("+ Add Text"));
    expect(screen.getByPlaceholderText(/Paste or type/)).toBeInTheDocument();
    expect(screen.getByText("Add Text")).toBeInTheDocument();
  });

  it("abre el formulario Add File", async () => {
    render(<KnowledgeBase />);
    await screen.findByText("notes.txt");

    fireEvent.click(screen.getByText("+ Add File"));
    expect(screen.getByPlaceholderText(/Full file path/)).toBeInTheDocument();
  });

  it("agrega texto mediante el formulario", async () => {
    vi.mocked(kb.addText).mockResolvedValue({ doc_id: "new-doc", status: "ok" });
    render(<KnowledgeBase />);
    await screen.findByText("notes.txt");

    fireEvent.click(screen.getByText("+ Add Text"));
    fireEvent.change(screen.getByPlaceholderText(/Paste or type/), { target: { value: "test content" } });
    fireEvent.change(screen.getAllByPlaceholderText(/Source/)[0], { target: { value: "test.txt" } });
    fireEvent.click(screen.getByText("Add Text"));

    await waitFor(() => {
      expect(kb.addText).toHaveBeenCalledWith("test content", "test.txt", undefined);
    });
  });

  it("agrega archivo mediante el formulario", async () => {
    vi.mocked(kb.addFile).mockResolvedValue({ doc_id: "file-doc", status: "ok" });
    render(<KnowledgeBase />);
    await screen.findByText("notes.txt");

    fireEvent.click(screen.getByText("+ Add File"));
    fireEvent.change(screen.getByPlaceholderText(/Full file path/), { target: { value: "C:\\docs\\report.txt" } });
    fireEvent.click(screen.getByText("Add File"));

    await waitFor(() => {
      expect(kb.addFile).toHaveBeenCalledWith("C:\\docs\\report.txt");
    });
  });

  it("elimina un documento", async () => {
    vi.mocked(kb.delete).mockResolvedValue({ doc_id: "doc1", removed: true });
    render(<KnowledgeBase />);
    await screen.findByText("notes.txt");

    const delButtons = screen.getAllByText("Del");
    fireEvent.click(delButtons[0]);

    await waitFor(() => expect(kb.delete).toHaveBeenCalledWith("doc1"));
  });

  it("abre y ejecuta búsqueda semántica", async () => {
    vi.mocked(kb.search).mockResolvedValue({
      results: [{ text: "relevant content", source: "notes.txt", score: 0.92 }],
      count: 1,
    });
    render(<KnowledgeBase />);
    await screen.findByText("notes.txt");

    fireEvent.click(screen.getByText("Search"));
    fireEvent.change(screen.getByPlaceholderText("Search query..."), { target: { value: "test query" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => {
      expect(kb.search).toHaveBeenCalledWith("test query", 10);
    });
    expect(await screen.findByText("relevant content")).toBeInTheDocument();
    expect(screen.getByText("92% match")).toBeInTheDocument();
  });

  it("muestra estado vacío sin documentos", async () => {
    vi.mocked(kb.list).mockResolvedValue({ documents: [], total: 0 });
    render(<KnowledgeBase />);
    expect(await screen.findByText(/No documents/)).toBeInTheDocument();
  });
});
