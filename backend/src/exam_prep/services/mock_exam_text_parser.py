import re
from dataclasses import dataclass, field
from typing import Final

from exam_prep.schemas.exam import MockExamSourceOption

QUESTION_RE: Final = re.compile(r"^(?P<number>\d{1,3})[.)]\s+(?P<body>.+)$")
OPTION_RE: Final = re.compile(r"^(?P<option>[A-H])[.)]\s+(?P<body>.+)$", re.IGNORECASE)
ANSWER_RE: Final = re.compile(
    r"^(?P<number>\d{1,3})[.)]\s*(?P<option>[A-H])(?:[.)])?\s*(?P<body>.*)$",
    re.IGNORECASE,
)
EXAM_HEADING_RE: Final = re.compile(
    r"^(?!Answer)(?P<title>.*?\b(?:(?:Practice|Mock|Sample)\s+)?(?:Exam|Test)\s+"
    r"(?P<exam>[0-9A-Z]+))\b",
    re.IGNORECASE,
)
ANSWER_HEADING_RE: Final = re.compile(
    r"^(?:Answer\s+Key|Answers?)(?:\s+(?:for|to))?\s+.*?"
    r"(?:(?:Practice|Mock|Sample)\s+)?(?:Exam|Test)\s+(?P<exam>[0-9A-Z]+)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ParsedQuestion:
    """Mutable parsed question accumulator used before Pydantic source-question creation."""

    question_number: int
    prompt: str
    options: list[MockExamSourceOption]
    source_page: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedAnswer:
    correct_option_id: str | None
    explanation: str


@dataclass(slots=True)
class ExamLines:
    """Mutable text-bank bucket for question and answer lines from one source exam."""

    title: str
    questions: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)


def split_exam_lines(pages: list[tuple[int, str]]) -> list[ExamLines]:
    exams: dict[str, ExamLines] = {}
    current_key = "1"
    mode = "questions"
    exams[current_key] = ExamLines(title="Practice Exam 1")
    for page_number, page_text in pages:
        for raw_line in page_text.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue
            answer_match = ANSWER_HEADING_RE.match(line)
            if answer_match:
                current_key = answer_match.group("exam").upper()
                exams.setdefault(current_key, ExamLines(title=f"Practice Exam {current_key}"))
                mode = "answers"
                continue
            exam_match = EXAM_HEADING_RE.match(line)
            if exam_match:
                current_key = exam_match.group("exam").upper()
                detected_title = exam_match.group("title").strip()
                existing = exams.get(current_key)
                if existing is None:
                    exams[current_key] = ExamLines(title=detected_title)
                elif not existing.questions and not existing.answers:
                    existing.title = detected_title
                mode = "questions"
                continue
            target = exams[current_key]
            target.pages.append(page_number)
            if mode == "answers":
                target.answers.append(line)
            else:
                target.questions.append(line)
    return list(exams.values())


def parse_questions(lines: list[str], pages: list[int]) -> list[ParsedQuestion]:
    parsed: list[ParsedQuestion] = []
    number: int | None = None
    prompt_lines: list[str] = []
    options: list[MockExamSourceOption] = []
    current_option: str | None = None

    def flush() -> None:
        nonlocal number, prompt_lines, options, current_option
        if number is not None and prompt_lines and options:
            parsed.append(
                ParsedQuestion(
                    question_number=number,
                    prompt=" ".join(prompt_lines).strip(),
                    options=options,
                    source_page=pages[0] if pages else None,
                )
            )
        number = None
        prompt_lines = []
        options = []
        current_option = None

    for line in lines:
        question_match = QUESTION_RE.match(line)
        option_match = OPTION_RE.match(line)
        if question_match:
            flush()
            number = int(question_match.group("number"))
            prompt_lines.append(question_match.group("body").strip())
        elif option_match and number is not None:
            current_option = option_match.group("option").upper()
            options.append(
                MockExamSourceOption(
                    option_id=current_option,
                    text=option_match.group("body").strip(),
                )
            )
        elif current_option and options:
            options[-1] = options[-1].model_copy(update={"text": f"{options[-1].text} {line}".strip()})
        elif number is not None:
            prompt_lines.append(line)
    flush()
    return parsed


def parse_answers(lines: list[str]) -> dict[int, ParsedAnswer]:
    answers: dict[int, ParsedAnswer] = {}
    current_number: int | None = None
    for line in lines:
        answer_match = ANSWER_RE.match(line)
        if answer_match:
            current_number = int(answer_match.group("number"))
            answers[current_number] = ParsedAnswer(
                correct_option_id=answer_match.group("option").upper(),
                explanation=answer_match.group("body").strip(),
            )
        elif current_number is not None:
            current = answers[current_number]
            answers[current_number] = ParsedAnswer(
                correct_option_id=current.correct_option_id,
                explanation=f"{current.explanation} {line}".strip(),
            )
    return answers
