import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppFrame } from "@/components/shared/app-frame";

vi.mock("@/components/shared/context-selector", () => ({
  ContextSelector: () => <div>Mock context selector</div>
}));

describe("AppFrame", () => {
  it("renders the compact working-page header content", () => {
    render(
      <AppFrame
        currentSlug="quiz"
        eyebrow="Study"
        title="Quiz"
        description="Generate grounded practice from the active study scope."
      >
        <div>Body</div>
      </AppFrame>
    );

    expect(screen.getByText("Study")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Quiz" })).toBeInTheDocument();
    expect(
      screen.getByText("Generate grounded practice from the active study scope.")
    ).toBeInTheDocument();
    expect(screen.getByText("Mock context selector")).toBeInTheDocument();
  });
});
