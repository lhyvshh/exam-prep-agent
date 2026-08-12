import { redirect } from "next/navigation";

export default async function CourseMockExamPage({
  params
}: {
  params: Promise<{ courseId: string }>;
}): Promise<never> {
  const { courseId } = await params;
  redirect(`/courses?mockExamCourseId=${encodeURIComponent(courseId)}`);
}
