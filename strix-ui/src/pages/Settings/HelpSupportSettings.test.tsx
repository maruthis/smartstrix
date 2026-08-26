import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import HelpSupportSettings from "./HelpSupportSettings";

describe("HelpSupportSettings", () => {
  it("renders documentation and support links", () => {
    render(<HelpSupportSettings />);
    expect(screen.getByRole("link", { name: "Documentation" })).toHaveAttribute("href", "https://github.com/usestrix/strix");
    expect(screen.getByRole("link", { name: "Contact support" })).toHaveAttribute("href", "mailto:support@example.com");
  });
});
