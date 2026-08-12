import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfigForm } from "@/components/config/config-form";

const fetchMock = vi.fn();

vi.stubGlobal("fetch", fetchMock);

function mockJsonResponse(payload: unknown): { readonly ok: true; readonly json: () => Promise<unknown> } {
  return {
    ok: true,
    json: async () => payload
  };
}

afterEach(() => {
  fetchMock.mockReset();
  cleanup();
});

describe("ConfigForm provider support", () => {
  it("treats Anthropic as a live provider in model setup", async () => {
    fetchMock
      .mockResolvedValueOnce(
        mockJsonResponse({
          config: {
            provider: "anthropic",
            model: "claude-sonnet-4-5",
            api_key: "sk-ant-test",
            demo_mode: false
          },
          butler_config: {
            provider: "anthropic",
            model: "claude-sonnet-4-5",
            api_key: "sk-ant-test",
            demo_mode: false
          },
          parser_config: {
            provider: "openai",
            model: "gpt-5.4-parser",
            api_key: "sk-parser-test",
            demo_mode: false
          },
          source: "sqlite_store"
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          ok: true,
          status: "ready",
          config_present: true
        })
      );

    render(<ConfigForm />);

    expect(await screen.findByLabelText("Provider")).toHaveValue("anthropic");
    expect(screen.queryByText(/planned connector/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate configuration" })).toBeEnabled();
  });

  it("lets Butler and parser agents use separate model setup profiles", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(
        mockJsonResponse({
          config: {
            provider: "openai",
            model: "gpt-5.4-mini",
            api_key: "sk-current-test",
            demo_mode: false
          },
          butler_config: {
            provider: "anthropic",
            model: "claude-sonnet-4-5",
            api_key: "sk-butler-test",
            demo_mode: false
          },
          parser_config: {
            provider: "openai",
            model: "gpt-5.4-parser",
            api_key: "sk-parser-test",
            demo_mode: false
          },
          source: "sqlite_store"
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          ok: true,
          status: "ready",
          config_present: true
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          is_valid: true,
          status: "valid",
          message: "Live provider validation succeeded.",
          config: {
            provider: "openai",
            model: "gpt-5.4-parser",
            api_key: "sk-parser-test",
            demo_mode: false
          },
          can_proceed: true
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          ok: true,
          status: "ready",
          config_present: true
        })
      );

    render(<ConfigForm />);

    expect(await screen.findByRole("button", { name: "Set up model for Butler" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Set up model for parser agents" }));

    expect(screen.getByLabelText("Model")).toHaveValue("gpt-5.4-parser");
    await user.click(screen.getByRole("button", { name: "Validate configuration" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/config/validate?profile=parser",
        expect.objectContaining({ method: "POST" })
      );
    });
  });
});
