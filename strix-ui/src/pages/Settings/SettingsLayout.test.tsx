import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SettingsLayout } from "./SettingsLayout";

describe("SettingsLayout", () => {
  it("renders the nav and the nested route's content", () => {
    render(
      <MemoryRouter initialEntries={["/settings/members"]}>
        <Routes>
          <Route path="/settings" element={<SettingsLayout />}>
            <Route path="members" element={<div>Members content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByText("General")).toBeInTheDocument();
    expect(screen.getByText("Members content")).toBeInTheDocument();
  });
});
