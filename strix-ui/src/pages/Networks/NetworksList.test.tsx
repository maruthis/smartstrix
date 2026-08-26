import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import NetworksList from "./NetworksList";

describe("NetworksList", () => {
  it("explains that the feature is not available yet", () => {
    renderWithProviders(<NetworksList />);
    expect(screen.getByText("Networks")).toBeInTheDocument();
    expect(screen.getByText(/not available in this deployment yet/)).toBeInTheDocument();
  });
});
