import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Board } from "./Board";

interface Item {
  id: string;
  label: string;
}

describe("Board", () => {
  it("renders each column with its item count and cards", () => {
    const columns = [
      { key: "open", label: "Open", items: [{ id: "1", label: "First" }] as Item[] },
      { key: "done", label: "Done", items: [] as Item[] },
    ];
    render(<Board columns={columns} renderCard={(item) => <span>{item.label}</span>} />);

    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByText("Empty")).toBeInTheDocument();
  });
});
