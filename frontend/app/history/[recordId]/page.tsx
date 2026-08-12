import React, { Suspense } from "react";

import { HistoryReview } from "@/components/history/history-review";

export default async function HistoryRecordPage({
  params
}: {
  params: Promise<{ recordId: string }>;
}): Promise<JSX.Element> {
  const { recordId } = await params;
  return (
    <Suspense fallback={<p className="subtle">Opening saved attempt...</p>}>
      <HistoryReview recordId={recordId} />
    </Suspense>
  );
}
