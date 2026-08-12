import { redirect } from "next/navigation";

export default function MockExamPage(): never {
  redirect("/courses");
}
