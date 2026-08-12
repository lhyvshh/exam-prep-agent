import React from "react";
import type { ReactNode } from "react";

import { ContextSelector } from "@/components/shared/context-selector";
import { appSections } from "@/lib/schemas";

type AppFrameProps = {
  currentSlug: string;
  eyebrow: string;
  title: string;
  description: string;
  showContextSelector?: boolean;
  children: ReactNode;
};

export function AppFrame({
  currentSlug,
  eyebrow,
  title,
  description,
  showContextSelector = true,
  children
}: AppFrameProps): JSX.Element {
  return (
    <main className="page-shell">
      <section className="workspace-header">
        <div className="workspace-header-copy">
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <nav className="tab-row" aria-label="App sections">
          {appSections.map((section) => (
            <a
              className={`tab-link${section.slug === currentSlug ? " tab-link-active" : ""}`}
              href={sectionHref(section.slug)}
              key={section.slug}
            >
              {section.label}
            </a>
          ))}
        </nav>
        {showContextSelector ? <ContextSelector /> : null}
      </section>
      <div className="stack">{children}</div>
    </main>
  );
}

function sectionHref(slug: string): string {
  if (slug === "config") {
    return "/settings/models";
  }
  if (slug === "notifications") {
    return "/settings/notifications";
  }
  return `/${slug}`;
}
