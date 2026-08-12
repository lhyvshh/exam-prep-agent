import { Suspense } from "react";

import { ExamReview } from "@/components/history/exam-review";

export default async function ExamHistoryPage({
  params
}: {
  params: Promise<{ examId: string }>;
}): Promise<JSX.Element> {
  const { examId } = await params;
  return (
    <Suspense fallback={<p className="subtle">Opening saved exam...</p>}>
      <ExamReview examId={examId} />
    </Suspense>
  );
}
