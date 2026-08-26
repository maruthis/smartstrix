import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "./Modal";

describe("Modal", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <Modal open={false} onClose={() => {}} title="Hello">
        content
      </Modal>
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders title, description, and children when open", () => {
    render(
      <Modal open onClose={() => {}} title="Hello" description="A description">
        <div>body content</div>
      </Modal>
    );
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("A description")).toBeInTheDocument();
    expect(screen.getByText("body content")).toBeInTheDocument();
  });

  it("calls onClose when the backdrop is clicked", async () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Hello">
        body
      </Modal>
    );
    await userEvent.click(screen.getByText("body").closest(".fixed") as HTMLElement);
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when the close button is clicked, but not on content clicks", async () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Hello">
        <div>body</div>
      </Modal>
    );
    await userEvent.click(screen.getByText("body"));
    expect(onClose).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
