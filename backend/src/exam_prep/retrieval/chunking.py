import re
from dataclasses import dataclass

from exam_prep.schemas.materials import SourceChunk, SourceSection
from exam_prep.services.question_pipeline import workbookStyleProfiles

WORKBOOK_HEADING_RE = re.compile(
    r"^(?P<heading>LEARNING\s+OBJECTIVES|KEY\s+CONCEPTS|MODULE\s+QUIZ\s+(?P<quiz_module>\d+(?:\.\w+)*)|"
    r"ANSWER\s+KEY\s+FOR\s+MODULE\s+QUIZZES|ANSWER\s+KEY\s+FOR\s+MODULE\s+QUIZ\s+(?P<answer_module>\d+(?:\.\w+)*))$",
    re.IGNORECASE,
)
LEARNING_OUTCOME_RE = re.compile(r"\bLO\s*(?P<number>\d+)\s*(?:\.|\s)\s*(?P<letter>[a-z])\b", re.IGNORECASE)
QUESTION_NUMBER_RE = re.compile(r"^\s*(?P<number>\d+)\.\s+")


@dataclass(slots=True)
class _WorkbookSupportBlock:
    block_type: str
    heading: str
    text: str
    module_number: str | None
    char_start: int
    char_end: int


@dataclass(slots=True)
class ChunkingService:
    chunk_size: int = 1000
    overlap: int = 100

    def chunk_sections(self, sections: list[SourceSection]) -> list[SourceChunk]:
        chunks: list[SourceChunk] = []
        chunk_counter = 0

        for section in sections:
            text = section.text.strip()
            if not text:
                continue

            support_chunks, chunk_counter = self._workbook_support_chunks(
                section,
                next_chunk_number=chunk_counter + 1,
            )
            chunks.extend(support_chunks)

            start = 0
            text_length = len(text)
            while start < text_length:
                end = min(start + self.chunk_size, text_length)
                if end < text_length:
                    whitespace_boundary = text.rfind(" ", start, end)
                    if whitespace_boundary > start:
                        end = whitespace_boundary

                chunk_text = text[start:end].strip()
                if chunk_text:
                    chunk_counter += 1
                    chunks.append(
                        SourceChunk(
                            chunk_id=f"{section.material_id}-chunk-{chunk_counter}",
                            source_id=section.source_id,
                            material_id=section.material_id,
                            course_id=section.course_id,
                            module_id=section.module_id,
                            file_name=section.file_name,
                            content_type=section.content_type,
                            section_title=section.section_title,
                            text=chunk_text,
                            page_end=section.page_end,
                            token_count=max(1, len(chunk_text.split())),
                            section_kind=section.section_kind,
                            content_label=section.content_label,
                            priority_score=section.priority_score,
                            is_default=section.is_default,
                            locator=section.locator.model_copy(
                                update={"char_start": start, "char_end": end}
                            ),
                            citation_label=section.citation_label,
                        )
                    )

                if end >= text_length:
                    break

                start = max(end - self.overlap, start + 1)

        return chunks

    def _workbook_support_chunks(
        self,
        section: SourceSection,
        *,
        next_chunk_number: int,
    ) -> tuple[list[SourceChunk], int]:
        blocks = self._workbook_support_blocks(section.text)
        if not blocks:
            return [], next_chunk_number - 1

        section_learning_outcomes = self._learning_outcome_ids(section.text)
        answer_outcomes_by_module = {
            block.module_number: self._learning_outcome_ids(block.text)
            for block in blocks
            if block.block_type == "answer_key" and block.module_number is not None
        }
        chunks: list[SourceChunk] = []
        chunk_number = next_chunk_number
        for block in blocks:
            learning_outcome_ids = self._learning_outcome_ids(block.text)
            if block.block_type == "module_quiz" and block.module_number is not None:
                learning_outcome_ids = answer_outcomes_by_module.get(block.module_number, []) or learning_outcome_ids
            if not learning_outcome_ids:
                learning_outcome_ids = section_learning_outcomes

            chunks.append(
                SourceChunk(
                    chunk_id=f"{section.material_id}-chunk-{chunk_number}",
                    source_id=section.source_id,
                    material_id=section.material_id,
                    course_id=section.course_id,
                    module_id=section.module_id,
                    file_name=section.file_name,
                    content_type=section.content_type,
                    section_title=section.section_title,
                    text=block.text,
                    page_end=section.page_end,
                    token_count=max(1, len(block.text.split())),
                    section_kind=section.section_kind,
                    content_label=section.content_label,
                    priority_score=max(section.priority_score, 0.95),
                    is_default=section.is_default,
                    workbook_block_type=block.block_type,
                    workbook_module_number=block.module_number,
                    learning_outcome_ids=learning_outcome_ids,
                    module_quiz_question_numbers=(
                        self._question_numbers(block.text) if block.block_type == "module_quiz" else []
                    ),
                    module_quiz_answer_numbers=(
                        self._question_numbers(block.text) if block.block_type == "answer_key" else []
                    ),
                    module_quiz_style_profiles=(
                        workbookStyleProfiles(block.text) if block.block_type == "module_quiz" else []
                    ),
                    locator=section.locator.model_copy(
                        update={"char_start": block.char_start, "char_end": block.char_end}
                    ),
                    citation_label=section.citation_label,
                )
            )
            chunk_number += 1
        return chunks, chunk_number - 1

    def _workbook_support_blocks(self, text: str) -> list[_WorkbookSupportBlock]:
        lines = text.splitlines()
        headings: list[tuple[int, re.Match[str]]] = []
        cursor = 0
        inside_answer_key = False
        for line in lines:
            stripped = line.strip()
            match = WORKBOOK_HEADING_RE.match(stripped)
            if match is not None:
                heading = " ".join(match.group("heading").split()).lower()
                if heading.startswith("answer key"):
                    inside_answer_key = True
                    headings.append((cursor, match))
                elif inside_answer_key and heading.startswith("module quiz"):
                    pass
                else:
                    headings.append((cursor, match))
            cursor += len(line) + 1

        blocks: list[_WorkbookSupportBlock] = []
        for index, (char_start, match) in enumerate(headings):
            heading = " ".join(match.group("heading").split())
            block_type = self._workbook_block_type(heading)
            if block_type not in {"key_concepts", "module_quiz", "answer_key"}:
                continue
            char_end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
            block_text = text[char_start:char_end].strip()
            if not block_text:
                continue
            module_number = match.group("quiz_module") or match.group("answer_module")
            if block_type == "answer_key" and module_number is None:
                module_number = self._answer_key_module_number(block_text)
            blocks.append(
                _WorkbookSupportBlock(
                    block_type=block_type,
                    heading=heading,
                    text=block_text,
                    module_number=module_number,
                    char_start=char_start,
                    char_end=char_end,
                )
            )
        return blocks

    def _workbook_block_type(self, heading: str) -> str:
        normalized = " ".join(heading.lower().split())
        if normalized == "key concepts":
            return "key_concepts"
        if normalized.startswith("module quiz"):
            return "module_quiz"
        if normalized.startswith("answer key"):
            return "answer_key"
        return "learning_objectives"

    def _answer_key_module_number(self, text: str) -> str | None:
        match = re.search(r"\bMODULE\s+QUIZ\s+(?P<number>\d+(?:\.\w+)*)\b", text, re.IGNORECASE)
        if match is None:
            return None
        return match.group("number")

    def _learning_outcome_ids(self, text: str) -> list[str]:
        outcomes: list[str] = []
        for match in LEARNING_OUTCOME_RE.finditer(text):
            outcome = f"LO {int(match.group('number'))}.{match.group('letter').lower()}"
            if outcome not in outcomes:
                outcomes.append(outcome)
        return outcomes

    def _question_numbers(self, text: str) -> list[int]:
        numbers: list[int] = []
        for line in text.splitlines():
            match = QUESTION_NUMBER_RE.match(line)
            if match is None:
                continue
            number = int(match.group("number"))
            if number not in numbers:
                numbers.append(number)
        return numbers
