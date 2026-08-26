import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilterBar, Tabs } from "./FilterBar";

describe("FilterBar", () => {
  it("renders a search input and calls onSearch on typing", async () => {
    const onSearch = vi.fn();
    render(<FilterBar search="" onSearch={onSearch} placeholder="Search..." />);
    await userEvent.type(screen.getByPlaceholderText("Search..."), "x");
    expect(onSearch).toHaveBeenCalled();
  });

  it("renders children alongside the search input", () => {
    render(
      <FilterBar search="" onSearch={vi.fn()}>
        <button>Extra</button>
      </FilterBar>
    );
    expect(screen.getByRole("button", { name: "Extra" })).toBeInTheDocument();
  });

  it("omits the search input entirely when onSearch isn't provided", () => {
    render(<FilterBar>{null}</FilterBar>);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});

describe("Tabs", () => {
  const tabs = [
    { key: "all", label: "All", count: 3 },
    { key: "open", label: "Open" },
  ];

  it("renders tab labels and counts, marking the active one", () => {
    render(<Tabs tabs={tabs} active="all" onChange={vi.fn()} />);
    expect(screen.getByText("All")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Open")).toBeInTheDocument();
  });

  it("calls onChange with the clicked tab's key", async () => {
    const onChange = vi.fn();
    render(<Tabs tabs={tabs} active="all" onChange={onChange} />);
    await userEvent.click(screen.getByText("Open"));
    expect(onChange).toHaveBeenCalledWith("open");
  });
});
