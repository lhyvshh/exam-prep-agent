import React, { Suspense } from "react";

import { MaterialsWorkspace } from "@/components/materials/materials-workspace";
import { AppFrame } from "@/components/shared/app-frame";

export default function MaterialSourcePage(): JSX.Element {
  return (
    <AppFrame
      currentSlug="materials"
      eyebrow="Source"
      title="Material source"
      description="Review the uploaded material at the cited page or section."
    >
      <Suspense fallback={<p className="subtle">Loading material source...</p>}>
        <MaterialsWorkspace />
      </Suspense>
    </AppFrame>
  );
}
