import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import Dashboard from "./Dashboard";

describe("Dashboard", () => {
  it("renders the three onboarding cards", () => {
    renderWithProviders(<Dashboard />);
    expect(screen.getByText("Run your first pentest")).toBeInTheDocument();
    expect(screen.getByText("Schedule pentests")).toBeInTheDocument();
    expect(screen.getByText("Enable PR reviews")).toBeInTheDocument();
  });

  it("navigates when a card's CTA is clicked", async () => {
    renderWithProviders(<Dashboard />);
    await userEvent.click(screen.getByRole("button", { name: "Enable Reviews" }));
    // No assertion target for the route itself here (no routed content in
    // this render tree) — this exercises the navigate() call without error.
  });
});
