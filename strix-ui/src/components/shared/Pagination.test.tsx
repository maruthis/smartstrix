import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Pagination } from "./Pagination";

describe("Pagination", () => {
  it("renders nothing when there's only one page", () => {
    const { container } = render(<Pagination page={1} pageSize={50} total={10} onChange={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the current range and page count across multiple pages", () => {
    render(<Pagination page={2} pageSize={50} total={120} onChange={vi.fn()} />);
    expect(screen.getByText("51-100 of 120")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  });

  it("disables Previous on the first page and calls onChange(page+1) on Next", async () => {
    const onChange = vi.fn();
    render(<Pagination page={1} pageSize={50} total={120} onChange={onChange} />);
    const prev = screen.getByRole("button", { name: "Previous page" });
    const next = screen.getByRole("button", { name: "Next page" });
    expect(prev).toBeDisabled();
    expect(next).not.toBeDisabled();

    await userEvent.click(next);
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it("disables Next on the last page and calls onChange(page-1) on Previous", async () => {
    const onChange = vi.fn();
    render(<Pagination page={3} pageSize={50} total={120} onChange={onChange} />);
    const prev = screen.getByRole("button", { name: "Previous page" });
    const next = screen.getByRole("button", { name: "Next page" });
    expect(next).toBeDisabled();
    expect(prev).not.toBeDisabled();

    await userEvent.click(prev);
    expect(onChange).toHaveBeenCalledWith(2);
  });
});
