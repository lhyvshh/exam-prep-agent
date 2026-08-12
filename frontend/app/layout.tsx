import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { CourseSelectionProvider } from "@/components/shared/course-context";

export const metadata: Metadata = {
  title: "Exam Prep Agent | Course-first study workspace",
  description: "A local-first exam preparation workspace for source-grounded study, quizzes, mock exams, and review."
};

type RootLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProps): JSX.Element {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">Skip to content</a>
        <CourseSelectionProvider>{children}</CourseSelectionProvider>
      </body>
    </html>
  );
}
