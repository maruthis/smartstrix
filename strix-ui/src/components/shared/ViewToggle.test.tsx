import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ViewToggle } from "./ViewToggle";

describe("ViewToggle", () => {
  it("calls onChange with 'board' when Board is clicked", async () => {
    const onChange = vi.fn();
    render(<ViewToggle view="list" onChange={onChange} />);
    await userEvent.click(screen.getByText("Board"));
    expect(onChange).toHaveBeenCalledWith("board");
  });

  it("calls onChange with 'list' when List is clicked", async () => {
    const onChange = vi.fn();
    render(<ViewToggle view="board" onChange={onChange} />);
    await userEvent.click(screen.getByText("List"));
    expect(onChange).toHaveBeenCalledWith("list");
  });
});
