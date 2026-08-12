import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.schemas.exam import (
    MockExamSourceBank,
    MockExamSourceExam,
    MockExamSourceQuestion,
)
from exam_prep.schemas.materials import SourceChunk
from exam_prep.services.mock_exam_pdf_extractor import (
    extract_exam_source_pages,
    recover_exam_source_pages,
)
from exam_prep.services.mock_exam_scanned_parser import (
    ScannedExam,
    incomplete_scanned_question_pages,
    parse_scanned_frm_exam_pages,
)
from exam_prep.services.mock_exam_text_parser import (
    ExamLines,
    ParsedAnswer,
    ParsedQuestion,
    parse_answers,
    parse_questions,
    split_exam_lines,
)
LO_RE = re.compile(r"\bLO\s+(?P<number>\d+)\s*[.\s]\s*(?P<letter>[a-z])\b", re.IGNORECASE)
OBJECTIVE_RE = re.compile(
    r"\b(?:Learning\s+Objective|Objective)\s*(?:\d+(?:\.[A-Za-z0-9]+)*)?\s*:?\s*"
    r"(?P<text>[A-Z][^.!?\n]{4,160})",
    re.IGNORECASE,
)
STOP_WORDS = {
    "about",
    "after",
    "answer",
    "before",
    "best",
    "describes",
    "does",
    "following",
    "from",
    "into",
    "risk",
    "statement",
    "which",
    "with",
}


class MockExamSourceService:
    def __init__(self, *, material_store: MaterialStore, exam_store: ExamStore) -> None:
        self.material_store = material_store
        self.exam_store = exam_store
        self._chunk_index: dict[str, list[tuple[SourceChunk, set[str]]]] = {}

    def ingest_source_bank(
        self,
        *,
        course_id: str,
        file_name: str,
        content_type: str | None,
        data: bytes,
        enable_ocr: bool = False,
    ) -> MockExamSourceBank:
        if not data:
            raise MaterialIngestionError("Uploaded exam source is empty.")
        pages = extract_exam_source_pages(file_name=file_name, data=data, enable_ocr=enable_ocr)
        if enable_ocr and Path(file_name).suffix.lower() == ".pdf":
            pages = recover_exam_source_pages(
                data,
                pages,
                incomplete_scanned_question_pages(pages),
            )
        bank_id = uuid4().hex
        scanned_exams = parse_scanned_frm_exam_pages(pages)
        if scanned_exams:
            exams = [
                self._build_scanned_source_exam(
                    bank_id=bank_id,
                    course_id=course_id,
                    exam_index=index,
                    scanned_exam=scanned_exam,
                )
                for index, scanned_exam in enumerate(scanned_exams, start=1)
            ]
        else:
            exam_lines = split_exam_lines(pages)
            exams = [
                self._build_source_exam(
                    bank_id=bank_id,
                    course_id=course_id,
                    exam_index=index,
                    exam_lines=lines,
                )
                for index, lines in enumerate(exam_lines, start=1)
            ]
        exams = [exam for exam in exams if exam.questions]
        if not exams:
            raise MaterialIngestionError("No complete exam questions and answers were found.")

        bank = MockExamSourceBank(
            bank_id=bank_id,
            course_id=course_id,
            file_name=Path(file_name).name,
            content_type=content_type,
            uploaded_at=datetime.now(UTC).isoformat(),
            extraction_mode="ocr" if enable_ocr else "text",
            exams=exams,
            warnings=self._source_warnings(exams),
        )
        self.exam_store.save_source_bank(bank)
        return bank

    def _build_source_exam(
        self,
        *,
        bank_id: str,
        course_id: str,
        exam_index: int,
        exam_lines: ExamLines,
    ) -> MockExamSourceExam:
        source_exam_id = f"{bank_id}-exam-{exam_index}"
        answers = parse_answers(exam_lines.answers)
        questions = [
            self._classify_question(
                course_id=course_id,
                source_exam_id=source_exam_id,
                parsed_question=question,
                parsed_answer=answers.get(question.question_number),
            )
            for question in parse_questions(exam_lines.questions, exam_lines.pages)
        ]
        return MockExamSourceExam(
            source_exam_id=source_exam_id,
            title=exam_lines.title,
            question_count=len(questions),
            answer_count=len(answers),
            questions=questions,
        )

    def _build_scanned_source_exam(
        self,
        *,
        bank_id: str,
        course_id: str,
        exam_index: int,
        scanned_exam: ScannedExam,
    ) -> MockExamSourceExam:
        source_exam_id = f"{bank_id}-exam-{exam_index}"
        questions = [
            self._classify_question(
                course_id=course_id,
                source_exam_id=source_exam_id,
                parsed_question=ParsedQuestion(
                    question_number=question.question_number,
                    prompt=question.prompt,
                    options=list(question.options),
                    source_page=question.source_page,
                ),
                parsed_answer=ParsedAnswer(
                    correct_option_id=None,
                    explanation=question.explanation,
                )
                if question.explanation
                else None,
            )
            for question in scanned_exam.questions
        ]
        answer_count = sum(1 for question in scanned_exam.questions if question.explanation)
        return MockExamSourceExam(
            source_exam_id=source_exam_id,
            title=scanned_exam.title,
            question_count=len(questions),
            answer_count=answer_count,
            questions=questions,
        )

    def _classify_question(
        self,
        *,
        course_id: str,
        source_exam_id: str,
        parsed_question: ParsedQuestion,
        parsed_answer: ParsedAnswer | None,
    ) -> MockExamSourceQuestion:
        option_id = parsed_answer.correct_option_id if parsed_answer else None
        explanation = parsed_answer.explanation if parsed_answer else ""
        classification_text = " ".join(
            [
                parsed_question.prompt,
                *(option.text for option in parsed_question.options),
                explanation,
            ]
        )
        matched_chunk = self._best_matching_chunk(course_id, classification_text)
        correct_answer = explanation
        if not correct_answer and option_id:
            correct_answer = next(
                (option.text for option in parsed_question.options if option.option_id == option_id),
                "",
            )
        evidence = matched_chunk.text if matched_chunk else None
        learning_objective = self._learning_objective(parsed_question.prompt)
        if learning_objective is None and matched_chunk is not None:
            learning_objective = self._learning_objective(matched_chunk.text)
        return MockExamSourceQuestion(
            source_question_id=f"{source_exam_id}-source-q{parsed_question.question_number}",
            source_exam_id=source_exam_id,
            question_number=parsed_question.question_number,
            prompt=parsed_question.prompt,
            options=parsed_question.options,
            correct_option_id=option_id,
            correct_answer=correct_answer,
            explanation=explanation,
            topic=matched_chunk.section_title if matched_chunk else "Unclassified topic",
            learning_objective=learning_objective,
            difficulty=self._difficulty(classification_text),
            source_page=parsed_question.source_page,
            matched_material_id=matched_chunk.material_id if matched_chunk else None,
            matched_source_id=matched_chunk.source_id if matched_chunk else None,
            matched_chunk_id=matched_chunk.chunk_id if matched_chunk else None,
            matched_citation_label=matched_chunk.citation_label if matched_chunk else None,
            source_evidence=evidence,
        )

    @staticmethod
    def _difficulty(text: str) -> float:
        normalized = " ".join(text.casefold().split())
        difficult_markers = (
            "calculate",
            "compute",
            "estimate",
            "most likely",
            "least likely",
            "i.",
            "ii.",
            "iii.",
            "given that",
            "assume that",
        )
        if len(normalized.split()) >= 120 or any(
            marker in normalized for marker in difficult_markers
        ):
            return 0.8
        foundational_markers = (
            "is defined as",
            "best describes",
            "refers to",
            "what is",
            "which term",
        )
        if len(normalized.split()) <= 55 and any(
            marker in normalized for marker in foundational_markers
        ):
            return 0.3
        return 0.6

    def _best_matching_chunk(self, course_id: str, text: str) -> SourceChunk | None:
        query_tokens = self._tokens(text)
        best_score = 0
        best_chunk: SourceChunk | None = None
        for chunk, chunk_tokens in self._course_chunk_index(course_id):
            score = len(query_tokens & chunk_tokens)
            if score > best_score:
                best_score = score
                best_chunk = chunk
        return best_chunk

    def _course_chunk_index(self, course_id: str) -> list[tuple[SourceChunk, set[str]]]:
        cached = self._chunk_index.get(course_id)
        if cached is not None:
            return cached
        index = [
            (chunk, self._tokens(f"{chunk.section_title} {chunk.text}"))
            for document in self.material_store.list_parsed_documents_by_course(course_id, None)
            for chunk in document.chunks
        ]
        self._chunk_index[course_id] = index
        return index

    def _tokens(self, text: str) -> set[str]:
        return {
            token
            for token in re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()
            if len(token) >= 4 and token not in STOP_WORDS
        }

    def _learning_objective(self, text: str) -> str | None:
        match = LO_RE.search(text)
        if match is not None:
            return f"LO {match.group('number')}.{match.group('letter').lower()}"
        objective_match = OBJECTIVE_RE.search(text)
        if objective_match is None:
            return None
        return " ".join(objective_match.group("text").split()).strip(" .:;")

    def _source_warnings(self, exams: list[MockExamSourceExam]) -> list[str]:
        warnings: list[str] = []
        for exam in exams:
            numbers = sorted(question.question_number for question in exam.questions)
            if numbers and numbers != list(range(numbers[0], numbers[-1] + 1)):
                warnings.append(f"{exam.title} has gaps in its parsed question numbering.")
            if exam.answer_count < exam.question_count:
                warnings.append(f"{exam.title} has fewer parsed answers than questions.")
        return warnings
