import React from "react";
export function MaterialsSummary(): JSX.Element {
  return (
    <section className="card">
      <h3>Materials and indexing</h3>
      <p>
        Uploads now flow through the local ingestion and retrieval pipeline, storing section-aware
        chunks that later power quiz grounding, mock exams, and concept practice.
      </p>
    </section>
  );
}
