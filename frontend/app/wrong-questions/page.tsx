import { redirect } from "next/navigation";

export default function WrongQuestionsPage(): never {
  redirect("/courses");
}
