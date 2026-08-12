import React from "react";
import { appSections } from "@/lib/schemas";

export function ConfigSummary(): JSX.Element {
  return (
    <section className="card">
      <h3>Configuration slice</h3>
      <p>
        The system now validates runtime provider settings through the backend and exposes demo mode
        as the fast on-ramp for local exploration.
      </p>
      <div className="pill-row">
        {appSections.filter((section) => section.slug === "config").map((section) => (
          <span className="pill" key={section.slug}>
            {section.label}
          </span>
        ))}
      </div>
    </section>
  );
}
