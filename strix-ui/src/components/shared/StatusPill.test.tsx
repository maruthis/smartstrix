import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  it("renders a severity value with a humanized label by default", () => {
    render(<StatusPill value="critical" />);
    expect(screen.getByText("critical")).toBeInTheDocument();
  });

  it("renders a status value with underscores replaced by spaces", () => {
    render(<StatusPill value="in_progress" />);
    expect(screen.getByText("in progress")).toBeInTheDocument();
  });

  it("renders an unknown value with the default styling", () => {
    render(<StatusPill value="something_unmapped" />);
    expect(screen.getByText("something unmapped")).toBeInTheDocument();
  });

  it("renders a custom label when given", () => {
    render(<StatusPill value="verified" label="Verified" />);
    expect(screen.getByText("Verified")).toBeInTheDocument();
  });
});
