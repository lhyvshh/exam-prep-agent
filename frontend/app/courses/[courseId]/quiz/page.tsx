import { redirect } from "next/navigation";

export default async function CourseQuizPage({
  params
}: {
  params: Promise<{ courseId: string }>;
}): Promise<never> {
  const { courseId } = await params;
  redirect(`/courses/${encodeURIComponent(courseId)}/wrong-questions`);
}
