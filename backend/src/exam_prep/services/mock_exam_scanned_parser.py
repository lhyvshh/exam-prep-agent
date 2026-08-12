import re
from dataclasses import dataclass
from typing import Final

from exam_prep.schemas.exam import MockExamSourceOption

SCANNED_QUESTION_RE: Final = re.compile(
    r"^[QO]ue[s5][t7][iIl1][o0]n\s*#?\s*(?P<number>[0-9SOIl]{1,3})\s+of\s+"
    r"(?P<total>[0-9SOIl]{1,3})\b",
    re.IGNORECASE,
)
QUESTION_ID_RE: Final = re.compile(r"^Question\s+ID\s*[:=.'-]", re.IGNORECASE)
EXPLANATION_RE: Final = re.compile(r"^Explanat[iIl1S5]on$", re.IGNORECASE)
OPTION_LINE_RE: Final = re.compile(
    r"^(?P<option>[A-Da-d8АВСаЬсСВв•·]{1,2})[.),}]\s*(?P<body>.*)$",
    re.IGNORECASE,
)
EXPECTED_OPTION_IDS: Final = ("A", "B", "C", "D")
OCR_OPTION_LETTERS: Final = {
    "8": "B",
    "А": "A",
    "а": "A",
    "В": "B",
    "в": "B",
    "Ь": "B",
    "С": "C",
    "с": "C",
    "•": "D",
    "·": "D",
}


@dataclass(frozen=True, slots=True)
class ScannedExamQuestion:
    question_number: int
    prompt: str
    options: tuple[MockExamSourceOption, ...]
    explanation: str
    source_page: int | None


@dataclass(frozen=True, slots=True)
class ScannedExam:
    title: str
    questions: tuple[ScannedExamQuestion, ...]


@dataclass(frozen=True, slots=True)
class _QuestionBlock:
    question_number: int
    source_page: int | None
    lines: tuple[str, ...]


@dataclass(slots=True)
class _OptionDraft:
    option_id: str
    parts: list[str]


def parse_scanned_frm_exam_pages(pages: list[tuple[int, str]]) -> list[ScannedExam]:
    exam_blocks = _collect_question_sections(pages)
    parsed_exams = [
        ScannedExam(
            title=f"Practice Exam {exam_index}",
            questions=tuple(question for block in blocks if (question := _parse_question_block(block))),
        )
        for exam_index, blocks in enumerate(exam_blocks, start=1)
    ]
    explanations = [
        {
            block.question_number: explanation
            for block in blocks
            if (explanation := _parse_explanation(block))
        }
        for blocks in exam_blocks
    ]
    return _merge_question_and_answer_sections(parsed_exams, explanations)


def incomplete_scanned_question_pages(pages: list[tuple[int, str]]) -> set[int]:
    page_numbers: set[int] = set()
    for blocks in _collect_question_sections(pages):
        for block in blocks:
            if _parse_question_block(block) is not None or block.source_page is None:
                continue
            page_numbers.add(block.source_page)
            page_numbers.add(block.source_page + 1)
    return page_numbers


def _collect_question_sections(pages: list[tuple[int, str]]) -> list[list[_QuestionBlock]]:
    exam_blocks: list[list[_QuestionBlock]] = []
    current_exam: list[_QuestionBlock] = []
    current_number: int | None = None
    current_page: int | None = None
    current_lines: list[str] = []

    def flush_question() -> None:
        nonlocal current_number, current_page, current_lines
        if current_number is not None:
            current_exam.append(
                _QuestionBlock(
                    question_number=current_number,
                    source_page=current_page,
                    lines=tuple(current_lines),
                )
            )
        current_number = None
        current_page = None
        current_lines = []

    for page_number, page_text in pages:
        for raw_line in page_text.splitlines():
            line = _normalize_ocr_line(raw_line)
            if not line:
                continue
            question_match = SCANNED_QUESTION_RE.match(line)
            if question_match:
                question_number = _normalize_ocr_number(question_match.group("number"))
                previous_number = current_number
                flush_question()
                if current_exam and _starts_new_section(previous_number, question_number):
                    exam_blocks.append(current_exam)
                    current_exam = []
                current_number = question_number
                current_page = page_number
                continue
            if current_number is not None:
                current_lines.append(line)
    flush_question()
    if current_exam:
        exam_blocks.append(current_exam)
    return exam_blocks


def _starts_new_section(previous_number: int | None, question_number: int) -> bool:
    if previous_number is None:
        return False
    return question_number == 1 or (
        question_number < previous_number
        and (question_number <= 5 or previous_number - question_number >= 25)
    )


def _parse_question_block(block: _QuestionBlock) -> ScannedExamQuestion | None:
    prompt_lines: list[str] = []
    explanation_lines: list[str] = []
    option_drafts: list[_OptionDraft] = []
    option_index: int | None = None
    in_explanation = False

    line_index = 0
    while line_index < len(block.lines):
        line = block.lines[line_index]
        next_line = block.lines[line_index + 1] if line_index + 1 < len(block.lines) else None
        if QUESTION_ID_RE.match(line):
            line_index += 1
            continue
        if EXPLANATION_RE.match(line):
            in_explanation = True
            option_index = None
            line_index += 1
            continue
        if in_explanation:
            explanation_lines.append(line)
            line_index += 1
            continue
        option_match = OPTION_LINE_RE.match(line)
        if option_match:
            option_id = _normalize_option_id(option_match.group("option"))
            if not option_drafts and option_id != EXPECTED_OPTION_IDS[0]:
                first_option_parts = _split_unmarked_first_option(prompt_lines)
                if first_option_parts:
                    option_drafts.append(_OptionDraft(option_id=EXPECTED_OPTION_IDS[0], parts=first_option_parts))
            option_drafts.append(
                _OptionDraft(option_id=option_id, parts=_clean_option_parts([option_match.group("body")]))
            )
            option_index = len(option_drafts) - 1
            line_index += 1
            continue
        if option_index is not None and next_line:
            next_marker_option_id = _marker_only_option_id(next_line)
            if next_marker_option_id:
                option_drafts.append(_OptionDraft(option_id=next_marker_option_id, parts=[line]))
                option_index = len(option_drafts) - 1
                line_index += 2
                continue
        if option_index is not None:
            option_drafts[option_index].parts.append(line)
            line_index += 1
            continue
        prompt_lines.append(line)
        line_index += 1

    if not prompt_lines or not option_drafts:
        return None
    options_by_id = _finalize_option_drafts(option_drafts)
    if tuple(options_by_id) != EXPECTED_OPTION_IDS:
        return None
    return ScannedExamQuestion(
        question_number=block.question_number,
        prompt=" ".join(prompt_lines).strip(),
        options=tuple(options_by_id[option_id] for option_id in EXPECTED_OPTION_IDS),
        explanation=" ".join(explanation_lines).strip(),
        source_page=block.source_page,
    )


def _parse_explanation(block: _QuestionBlock) -> str:
    for index, line in enumerate(block.lines):
        if EXPLANATION_RE.match(line):
            return " ".join(block.lines[index + 1 :]).strip()
    return ""


def _normalize_ocr_line(raw_line: str) -> str:
    return " ".join(raw_line.replace("|", " ").split()).strip()


def _normalize_ocr_number(value: str) -> int:
    return int(value.upper().translate(str.maketrans("SOIL", "5011")))


def _normalize_option_id(value: str) -> str:
    if len(value) > 1:
        for character in reversed(value):
            normalized = OCR_OPTION_LETTERS.get(character, character.upper())
            if normalized in EXPECTED_OPTION_IDS:
                return normalized
    return OCR_OPTION_LETTERS.get(value, value.upper())


def _clean_option_parts(parts: list[str]) -> list[str]:
    return [part.strip() for part in parts if part.strip()]


def _marker_only_option_id(line: str) -> str | None:
    option_match = OPTION_LINE_RE.match(line)
    if not option_match or option_match.group("body").strip():
        return None
    return _normalize_option_id(option_match.group("option"))


def _split_unmarked_first_option(prompt_lines: list[str]) -> list[str]:
    for line_index in range(len(prompt_lines) - 2, -1, -1):
        if prompt_lines[line_index].endswith(("?", ":")):
            first_option_parts = prompt_lines[line_index + 1 :]
            del prompt_lines[line_index + 1 :]
            return first_option_parts
    return []


def _finalize_option_drafts(drafts: list[_OptionDraft]) -> dict[str, MockExamSourceOption]:
    drafts_by_id: dict[str, _OptionDraft] = {}
    for draft in drafts:
        draft.parts = _clean_option_parts(draft.parts)
        if not draft.parts:
            continue
        existing_draft = drafts_by_id.get(draft.option_id)
        if existing_draft:
            existing_draft.parts.extend(draft.parts)
        else:
            drafts_by_id[draft.option_id] = draft

    for index, option_id in enumerate(EXPECTED_OPTION_IDS):
        if option_id in drafts_by_id or index == 0:
            continue
        previous_id = EXPECTED_OPTION_IDS[index - 1]
        previous_draft = drafts_by_id.get(previous_id)
        if not previous_draft or len(previous_draft.parts) < 2:
            continue
        split_index = _split_index_for_missing_option(
            previous_id=previous_id,
            missing_id=option_id,
            part_count=len(previous_draft.parts),
        )
        inferred_parts = previous_draft.parts[split_index:]
        if not inferred_parts:
            continue
        previous_draft.parts = previous_draft.parts[:split_index]
        drafts_by_id[option_id] = _OptionDraft(option_id=option_id, parts=inferred_parts)

    return {
        option_id: MockExamSourceOption(option_id=option_id, text=" ".join(drafts_by_id[option_id].parts).strip())
        for option_id in EXPECTED_OPTION_IDS
        if option_id in drafts_by_id and drafts_by_id[option_id].parts
    }


def _split_index_for_missing_option(*, previous_id: str, missing_id: str, part_count: int) -> int:
    if previous_id == "B" and missing_id == "C" and part_count > 3:
        return part_count - 2
    if previous_id == "C" and missing_id == "D" and part_count > 3:
        return part_count - 2
    return 1


def _merge_question_and_answer_sections(
    exams: list[ScannedExam],
    explanations: list[dict[int, str]],
) -> list[ScannedExam]:
    merged_exams: list[ScannedExam] = []
    exam_index = 0
    while exam_index < len(exams):
        current_exam = exams[exam_index]
        next_exam = exams[exam_index + 1] if exam_index + 1 < len(exams) else None
        if (
            next_exam
            and not explanations[exam_index]
            and explanations[exam_index + 1]
        ):
            merged_exams.append(
                _merge_scanned_exam_pair(
                    current_exam,
                    next_exam,
                    answer_explanations=explanations[exam_index + 1],
                )
            )
            exam_index += 2
            continue
        merged_exams.append(current_exam)
        exam_index += 1
    return [
        ScannedExam(title=f"FRM Practice Exam {index}", questions=exam.questions)
        for index, exam in enumerate(merged_exams, start=1)
    ]


def _merge_scanned_exam_pair(
    question_exam: ScannedExam,
    answer_exam: ScannedExam,
    *,
    answer_explanations: dict[int, str],
) -> ScannedExam:
    questions_by_number = {question.question_number: question for question in question_exam.questions}
    answers_by_number = {question.question_number: question for question in answer_exam.questions}
    merged_questions = []
    for question_number in sorted(questions_by_number.keys() | answers_by_number.keys()):
        base_question = questions_by_number.get(question_number) or answers_by_number[question_number]
        answer_question = answers_by_number.get(question_number)
        merged_questions.append(
            ScannedExamQuestion(
                question_number=question_number,
                prompt=base_question.prompt,
                options=base_question.options,
                explanation=(
                    answer_explanations.get(question_number)
                    or (answer_question.explanation if answer_question else base_question.explanation)
                ),
                source_page=base_question.source_page,
            )
    )
    return ScannedExam(title=question_exam.title, questions=tuple(merged_questions))
