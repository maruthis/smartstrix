import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast, Toaster } from "./Toast";

describe("Toaster", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders nothing when there are no toasts", () => {
    const { container } = render(<Toaster />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a success toast and a distinct error toast", () => {
    render(<Toaster />);
    act(() => {
      toast.success("Saved");
      toast.error("Failed");
    });
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("dismisses a toast when its close button is clicked", async () => {
    render(<Toaster />);
    act(() => {
      toast.success("Click me away");
    });
    const message = screen.getByText("Click me away");
    const closeButton = message.parentElement!.querySelector("button")!;
    await userEvent.click(closeButton);
    expect(screen.queryByText("Click me away")).not.toBeInTheDocument();
  });

  it("auto-dismisses after the timeout", () => {
    vi.useFakeTimers();
    render(<Toaster />);
    act(() => {
      toast.success("Temporary");
    });
    expect(screen.getByText("Temporary")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryByText("Temporary")).not.toBeInTheDocument();
  });
});
