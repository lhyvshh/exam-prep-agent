"use client";

import React from "react";
import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";

import { fetchConfigHealth, fetchRuntimeConfig, validateConfig } from "@/lib/api";
import { MetricGrid } from "@/components/shared/data-widgets";
import type {
  ConfigHealthResponse,
  ConfigValidationResponse,
  LLMProvider,
  UserLLMConfig
} from "@/lib/schemas";

const providerOptions: Array<{ value: LLMProvider; label: string; live: boolean }> = [
  { value: "openai", label: "OpenAI", live: true },
  { value: "nvidia", label: "NVIDIA", live: true },
  { value: "anthropic", label: "Anthropic", live: true },
  { value: "google", label: "Google", live: false },
  { value: "groq", label: "Groq", live: false },
  { value: "openrouter", label: "OpenRouter", live: false },
  { value: "ollama", label: "Ollama / local", live: false },
  { value: "azure_openai", label: "Azure OpenAI", live: false }
];

const defaultFormState: UserLLMConfig = {
  provider: "openai",
  model: "gpt-5.4-mini",
  api_key: null,
  demo_mode: true
};

type ModelProfile = "current" | "butler" | "parser";

const modelProfileLabels: Record<ModelProfile, string> = {
  current: "Practice generator",
  butler: "Set up model for Butler",
  parser: "Set up model for parser agents"
};

export function ConfigForm({ compact = false }: { compact?: boolean } = {}): JSX.Element {
  const [formState, setFormState] = useState<UserLLMConfig>(defaultFormState);
  const [butlerState, setButlerState] = useState<UserLLMConfig>(defaultFormState);
  const [parserState, setParserState] = useState<UserLLMConfig>(defaultFormState);
  const [activeModelProfile, setActiveModelProfile] = useState<ModelProfile>("current");
  const [health, setHealth] = useState<ConfigHealthResponse | null>(null);
  const [result, setResult] = useState<ConfigValidationResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isBooting, setIsBooting] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const submitSequenceRef = useRef<number>(0);

  useEffect(() => {
    void loadInitialState();
  }, []);

  async function loadInitialState(): Promise<void> {
    setIsBooting(true);
    try {
      const [runtimeConfig, currentHealth] = await Promise.all([
        fetchRuntimeConfig(),
        fetchConfigHealth()
      ]);
      setFormState(runtimeConfig.config);
      setButlerState(runtimeConfig.butler_config ?? runtimeConfig.config);
      setParserState(runtimeConfig.parser_config ?? runtimeConfig.config);
      setHealth(currentHealth);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Unable to load config state.");
    } finally {
      setIsBooting(false);
    }
  }

  function updateField<K extends keyof UserLLMConfig>(key: K, value: UserLLMConfig[K]): void {
    if (activeModelProfile === "butler") {
      setButlerState((current) => ({
        ...current,
        [key]: value
      }));
      return;
    }
    if (activeModelProfile === "parser") {
      setParserState((current) => ({
        ...current,
        [key]: value
      }));
      return;
    }
    setFormState((current) => ({
      ...current,
      [key]: value
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (isLoading) {
      return;
    }

    const submitSequence = submitSequenceRef.current + 1;
    submitSequenceRef.current = submitSequence;
    setIsLoading(true);
    setLoadError(null);
    setResult(null);

    try {
      const activeConfig = activeModelProfile === "butler"
        ? butlerState
        : activeModelProfile === "parser"
          ? parserState
          : formState;
      const validation = await validateConfig(activeConfig, activeModelProfile);
      if (submitSequence !== submitSequenceRef.current) {
        return;
      }
      setResult(validation);
      const nextHealth = await fetchConfigHealth();
      if (submitSequence !== submitSequenceRef.current) {
        return;
      }
      setHealth(nextHealth);
      if (activeModelProfile === "butler") {
        setButlerState(validation.config);
      } else if (activeModelProfile === "parser") {
        setParserState(validation.config);
      } else {
        setFormState(validation.config);
      }
    } catch (error) {
      if (submitSequence !== submitSequenceRef.current) {
        return;
      }
      setLoadError(error instanceof Error ? error.message : "Validation request failed.");
    } finally {
      if (submitSequence === submitSequenceRef.current) {
        setIsLoading(false);
      }
    }
  }

  const activeConfig = activeModelProfile === "butler"
    ? butlerState
    : activeModelProfile === "parser"
      ? parserState
      : formState;
  const metrics = [
    {
      label: "Runtime",
      value: health?.status ?? (isBooting ? "Loading..." : "Unknown")
    },
    {
      label: "Mode",
      value: activeConfig.demo_mode ? "Demo" : "Live"
    },
    {
      label: "Provider",
      value: activeConfig.provider
    }
  ];
  const selectedProvider = providerOptions.find((option) => option.value === activeConfig.provider);
  const liveProviderSupported = selectedProvider?.live ?? false;
  const canValidate = !isLoading && (activeConfig.demo_mode || liveProviderSupported);

  return (
    <div className="stack">
      {!compact ? <MetricGrid items={metrics} /> : null}

      <section className={`card${compact ? " compact-config-card" : ""}`}>
        <h3>LLM access configuration</h3>
        <p>
          {compact
            ? "Set models for practice generation, Butler, or parser agents, then validate."
            : "Use separate model profiles for practice generation, Exam Butler, and parser agents. Butler is the TA chat model; parser agents handle ingestion and book-structure work."}
        </p>
        {compact ? (
          <div className="compact-config-metrics">
            {metrics.map((item) => (
              <span className="pill" key={item.label}>
                {item.label}: {item.value}
              </span>
            ))}
          </div>
        ) : null}
        <form aria-busy={isLoading} className={`config-form${compact ? " compact-config-form" : ""}`} onSubmit={handleSubmit}>
          <div className="model-profile-switch" role="group" aria-label="Model profile">
            {(["current", "butler", "parser"] as ModelProfile[]).map((profile) => (
              <button
                aria-pressed={activeModelProfile === profile}
                className={activeModelProfile === profile ? "active" : ""}
                key={profile}
                onClick={() => setActiveModelProfile(profile)}
                type="button"
              >
                {modelProfileLabels[profile]}
              </button>
            ))}
          </div>

          <div className="two-column-grid">
            <label className="field">
              <span>Provider</span>
              <select
                aria-label="Provider"
                value={activeConfig.provider}
                onChange={(event) => updateField("provider", event.target.value as LLMProvider)}
              >
                {providerOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}{option.live ? " · live" : " · planned"}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Model</span>
              <input
                aria-label="Model"
                type="text"
                value={activeConfig.model}
                onChange={(event) => updateField("model", event.target.value)}
                placeholder="gpt-5.4-mini"
              />
            </label>
          </div>

          <label className="field">
            <span>API key</span>
            <input
              aria-label="API key"
              type="password"
              value={activeConfig.api_key ?? ""}
              onChange={(event) => updateField("api_key", event.target.value || null)}
              placeholder="sk-..."
              disabled={activeConfig.demo_mode}
            />
          </label>

          <label className="toggle">
            <input
              aria-label="Demo mode"
              type="checkbox"
              checked={activeConfig.demo_mode}
              onChange={(event) => updateField("demo_mode", event.target.checked)}
            />
            <span>Enable demo mode</span>
          </label>

          {!liveProviderSupported ? (
            <div className="status-panel" aria-live="polite">
              <strong>Provider status:</strong> {selectedProvider?.label ?? activeConfig.provider} is shown as a planned connector in this local build. Use demo mode for showcase routing, or choose OpenAI, NVIDIA, or Anthropic for live validation.
            </div>
          ) : null}

          <button className="primary-button" disabled={!canValidate} type="submit">
            {isLoading ? "Validating..." : !activeConfig.demo_mode && !liveProviderSupported ? "Provider planned" : "Validate configuration"}
          </button>
        </form>

        {result ? (
          <div className="status-panel" aria-live="polite">
            <strong>Validation:</strong> {result.message}
          </div>
        ) : null}

        {loadError ? (
          <div className="status-panel error-panel" aria-live="polite">
            <strong>Issue:</strong> {loadError}
          </div>
        ) : null}
      </section>
    </div>
  );
}
