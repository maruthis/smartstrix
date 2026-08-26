import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState, QueryStatus } from "./EmptyState";

describe("EmptyState", () => {
  it("renders title only", () => {
    render(<EmptyState title="No items" />);
    expect(screen.getByText("No items")).toBeInTheDocument();
  });

  it("renders icon, description, and action when given", () => {
    render(
      <EmptyState
        icon={<span data-testid="icon" />}
        title="No items"
        description="Add one to get started"
        action={<button>Add</button>}
      />
    );
    expect(screen.getByTestId("icon")).toBeInTheDocument();
    expect(screen.getByText("Add one to get started")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });
});

describe("QueryStatus", () => {
  it("shows a loading message", () => {
    render(<QueryStatus isLoading />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows an error message when not loading", () => {
    render(<QueryStatus isLoading={false} />);
    expect(screen.getByText(/Couldn't load this page/)).toBeInTheDocument();
  });
});
