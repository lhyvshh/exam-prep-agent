import React from "react";

import { ConfigForm } from "@/components/config/config-form";
import { AppFrame } from "@/components/shared/app-frame";

const taskRoutes = [
  "Parsing",
  "Study enrichment",
  "Quiz generation",
  "Mock exam generation",
  "Explanation",
  "Agent planning"
];

export default function ModelSettingsPage(): JSX.Element {
  return (
    <AppFrame
      currentSlug="config"
      eyebrow="Settings"
      title="Model hub"
      description="Connect providers and keep task routing simple: Auto-recommended by default, explicit model choices when needed."
      showContextSelector={false}
    >
      <div className="stack">
        <section className="card">
          <div className="section-header">
            <div>
              <h3>Task routing profile</h3>
              <p className="subtle">The current build stores one validated runtime provider. These task slots make the final routing model visible without creating chaos.</p>
            </div>
            <span className="quality-badge">Auto-recommended</span>
          </div>
          <div className="model-route-grid">
            {taskRoutes.map((task) => (
              <article className="model-route-card" key={task}>
                <strong>{task}</strong>
                <span>Auto-recommended provider/model</span>
              </article>
            ))}
          </div>
        </section>
        <ConfigForm />
      </div>
    </AppFrame>
  );
}
