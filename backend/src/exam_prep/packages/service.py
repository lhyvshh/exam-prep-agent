from datetime import UTC, datetime
from pathlib import Path
from typing import assert_never
from uuid import uuid4

from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from ..repositories.package_store import PackageStore
from exam_prep.schemas.exam import StoredMockExamSession
from exam_prep.schemas.quiz import (
    ExamQuestionCategory,
    QuestionStyle,
    QuizQuestion,
    StoredQuestionKey,
)
from exam_prep.services.section_study_service import SectionStudyService
from exam_prep.services.mock_exam_generation_service import MockExamGenerationService

from .assembler import PackageAssembler, PackageAssemblyResult
from .curriculum import CurriculumSnapshot, CurriculumSnapshotBuilder
from .frm_policy import FRM_PART_I_POLICY
from .models import (
    ExamBlueprintMode,
    OfflineExamQuestion,
    OfflineMockExam,
    PackageCreateRequest,
    PackageFile,
    PackageKind,
    PackageRecord,
    PackageStatus,
    PackageValidationReport,
    PackageVersion,
    PackageVersionResponse,
)
from .validation import (
    PackageBuildSnapshot,
    PackageValidator,
    SourceExamProfile,
    SourceExamQuestionProfile,
)


class PackageServiceError(RuntimeError):
    pass


class PackageNotFoundError(PackageServiceError):
    pass


class PackageBuildError(PackageServiceError):
    pass


class PackageService:
    def __init__(
        self,
        *,
        package_store: PackageStore,
        material_store: MaterialStore,
        exam_store: ExamStore,
        storage_root: Path,
    ) -> None:
        self.package_store = package_store
        self.material_store = material_store
        self.exam_store = exam_store
        self.assembler = PackageAssembler(storage_root)
        self.validator = PackageValidator()
        self.study_service = SectionStudyService(material_store)

    def create(self, request: PackageCreateRequest) -> PackageRecord:
        now = self._now()
        record = PackageRecord(
            package_id=uuid4().hex,
            course_id=request.course_id,
            title=request.title,
            package_kind=request.package_kind,
            exam_name=request.exam_name,
            exam_part=request.exam_part,
            status=PackageStatus.DRAFT,
            active_version=1,
            created_at=now,
            updated_at=now,
        )
        version = PackageVersion(
            package_id=record.package_id,
            version=1,
            status=PackageStatus.DRAFT,
            configuration=request,
            created_at=now,
            source_fingerprint=self._source_fingerprint(request),
        )
        self.package_store.create_package(record)
        self.package_store.save_version(version)
        return record

    def get(self, package_id: str) -> PackageRecord:
        record = self.package_store.get_package(package_id)
        if record is None:
            raise PackageNotFoundError(f"Package not found: {package_id}")
        return record

    def list_packages(self, course_id: str) -> list[PackageRecord]:
        return self.package_store.list_packages(course_id)

    def prepare_build(self, package_id: str) -> PackageVersion:
        package = self.get(package_id)
        version = self._version_for_build(package)
        if version.version == package.active_version:
            return version
        now = self._now()
        self.package_store.save_version(version)
        self.package_store.create_package(
            package.model_copy(
                update={
                    "status": PackageStatus.DRAFT,
                    "active_version": version.version,
                    "updated_at": now,
                }
            )
        )
        return version

    def get_version(self, package_id: str) -> PackageVersion:
        package = self.get(package_id)
        return self.get_version_number(package_id, package.active_version)

    def get_version_number(self, package_id: str, version_number: int) -> PackageVersion:
        self.get(package_id)
        version = self.package_store.get_version(package_id, version_number)
        if version is None:
            raise PackageNotFoundError(
                f"Package version not found: {package_id} v{version_number}"
            )
        return version

    def list_versions(self, package_id: str) -> list[PackageVersion]:
        self.get(package_id)
        return self.package_store.list_versions(package_id)

    def get_version_response(
        self,
        package_id: str,
        version_number: int,
    ) -> PackageVersionResponse:
        package = self.get(package_id)
        version = self.get_version_number(package_id, version_number)
        return PackageVersionResponse(
            package=package,
            version=version,
            files=tuple(self.package_store.list_files(package_id, version_number)),
            validation=self.package_store.get_validation(package_id, version_number),
        )

    def build(self, package_id: str) -> PackageAssemblyResult:
        version = self.prepare_build(package_id)
        package = self.get(package_id)
        now = self._now()
        building_package = package.model_copy(
            update={
                "status": PackageStatus.BUILDING,
                "active_version": version.version,
                "updated_at": now,
            }
        )
        self.package_store.create_package(
            building_package
        )
        self.package_store.save_version(
            version.model_copy(update={"status": PackageStatus.BUILDING})
        )
        snapshot = self._snapshot(building_package, version)
        result = self.assembler.assemble(snapshot)
        completed_at = self._now()
        self.package_store.replace_files(package_id, version.version, list(result.files))
        self.package_store.save_validation(result.manifest.validation)
        self.package_store.save_version(
            version.model_copy(
                update={
                    "status": PackageStatus.COMPLETE,
                    "completed_at": completed_at,
                    "model_metadata": result.manifest.model_metadata,
                    "prompt_versions": result.manifest.prompt_versions,
                }
            )
        )
        self.package_store.create_package(
            building_package.model_copy(
                update={
                    "status": PackageStatus.COMPLETE,
                    "updated_at": completed_at,
                }
            )
        )
        return result

    def validate(self, package_id: str) -> PackageValidationReport:
        package = self.get(package_id)
        version = self.get_version(package_id)
        report = self.validator.validate(self._snapshot(package, version))
        self.package_store.save_validation(report)
        return report

    def mark_failed(self, package_id: str) -> None:
        package = self.get(package_id)
        version = self.get_version(package_id)
        now = self._now()
        self.package_store.create_package(
            package.model_copy(update={"status": PackageStatus.FAILED, "updated_at": now})
        )
        self.package_store.save_version(version.model_copy(update={"status": PackageStatus.FAILED}))

    def list_files(self, package_id: str) -> list[PackageFile]:
        package = self.get(package_id)
        return self.package_store.list_files(package_id, package.active_version)

    def resolve_file(self, package_id: str, file_id: str) -> tuple[PackageFile, Path]:
        package = self.get(package_id)
        version = self.get_version(package_id)
        if package.status != PackageStatus.COMPLETE or version.status != PackageStatus.COMPLETE:
            raise PackageBuildError("Package download is unavailable until build completes.")
        return self.resolve_version_file(package_id, package.active_version, file_id)

    def resolve_version_file(
        self,
        package_id: str,
        version_number: int,
        file_id: str,
    ) -> tuple[PackageFile, Path]:
        version = self.get_version_number(package_id, version_number)
        if version.status != PackageStatus.COMPLETE:
            raise PackageBuildError("Package version download is unavailable until build completes.")
        report = self.package_store.get_validation(package_id, version_number)
        if report is None or not report.passed:
            raise PackageBuildError("Package download is unavailable until validation passes.")
        file = next(
            (
                item
                for item in self.package_store.list_files(package_id, version_number)
                if item.file_id == file_id
            ),
            None,
        )
        if file is None or file.artifact_path is None:
            raise PackageNotFoundError(f"Package file not found: {file_id}")
        root = self.assembler.storage_root.resolve()
        path = (root / file.artifact_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise PackageNotFoundError(f"Package artifact is unavailable: {file_id}")
        return file, path

    def _version_for_build(self, package: PackageRecord) -> PackageVersion:
        active = self.get_version(package.package_id)
        if active.status != PackageStatus.COMPLETE:
            return active
        now = self._now()
        return PackageVersion(
            package_id=package.package_id,
            version=active.version + 1,
            status=PackageStatus.DRAFT,
            configuration=active.configuration,
            created_at=now,
            source_fingerprint=self._source_fingerprint(active.configuration),
        )

    def _snapshot(
        self,
        package: PackageRecord,
        version: PackageVersion,
    ) -> PackageBuildSnapshot:
        course_materials = self.material_store.list_records_by_course(package.course_id)
        if not course_materials:
            raise PackageBuildError("No course materials are available for package generation.")
        configured_ids = version.configuration.material_ids
        if configured_ids:
            material_by_id = {material.material_id: material for material in course_materials}
            missing_ids = [material_id for material_id in configured_ids if material_id not in material_by_id]
            if missing_ids:
                raise PackageBuildError(
                    "Selected package materials are unavailable: " + ", ".join(missing_ids)
                )
            materials = [material_by_id[material_id] for material_id in configured_ids]
        else:
            materials = course_materials
        match version.configuration.package_kind:
            case PackageKind.COMPLETE:
                if (
                    version.configuration.exam_blueprint_mode == ExamBlueprintMode.FRM_PART_I
                    and len(materials) != 4
                ):
                    raise PackageBuildError(
                        f"Complete package requires exactly four course books; found {len(materials)}."
                    )
            case PackageKind.STUDY_CARDS | PackageKind.MOCK_EXAM:
                if not 1 <= len(materials) <= 32:
                    raise PackageBuildError(
                        f"Focused package requires one to 32 course books; found {len(materials)}."
                    )
            case unreachable:
                assert_never(unreachable)
        source_exam_id = version.configuration.source_exam_id
        selected_source_exam = None
        if source_exam_id is not None:
            selected_source_exam = next(
                (
                    exam
                    for bank in self.exam_store.list_source_banks_by_course(package.course_id)
                    for exam in bank.exams
                    if exam.source_exam_id == source_exam_id
                ),
                None,
            )
            if selected_source_exam is None:
                raise PackageBuildError(
                    f"Selected source exam is unavailable for this course: {source_exam_id}"
                )
        study_documents = [
            document
            for material in materials
            if (document := self.material_store.get_study_document(material.material_id))
            is not None
        ]
        if len(study_documents) != len(materials):
            raise PackageBuildError(
                "Every course material must finish study extraction before build."
            )
        curriculum_builder = CurriculumSnapshotBuilder()
        curriculum = curriculum_builder.build(
            course_id=package.course_id,
            materials=materials,
            study_documents=study_documents,
        )
        if version.configuration.package_kind != PackageKind.MOCK_EXAM:
            repair_ids = self._materials_requiring_card_repair(
                curriculum,
                version.configuration.cards_per_concept,
            )
            if repair_ids:
                documents_by_id = {
                    document.material_id: document for document in study_documents
                }
                for material_id in repair_ids:
                    repaired = self.study_service.ensure_study_document(
                        material_id,
                        force=True,
                    )
                    if repaired is not None:
                        documents_by_id[material_id] = repaired
                study_documents = [
                    documents_by_id[material.material_id] for material in materials
                ]
                curriculum = curriculum_builder.build(
                    course_id=package.course_id,
                    materials=materials,
                    study_documents=study_documents,
                )
        expected = version.configuration.mock_exam_count
        generated_exam_ids = version.configuration.generated_exam_ids
        if generated_exam_ids:
            sessions = []
            for exam_id in generated_exam_ids:
                session = self.exam_store.get_exam_session(exam_id)
                if session is None or session.exam.course_id != package.course_id:
                    raise PackageBuildError(
                        f"Selected generated exam is unavailable for this course: {exam_id}"
                    )
                sessions.append(session)
        elif expected:
            sessions = self.exam_store.list_exam_sessions_by_course(package.course_id)
        else:
            sessions = []
        if len(sessions) < expected:
            raise PackageBuildError(
                f"Package requires {expected} generated mock exam(s); found {len(sessions)}."
            )
        exams = tuple(
            self._offline_exam(
                index,
                session,
                timer_minutes=version.configuration.timer_minutes,
            )
            for index, session in enumerate(sessions[:expected], start=1)
        )
        prompt_versions = {
            document.material_id: f"section-study-v{document.pipeline_version}"
            for document in study_documents
        } | version.prompt_versions
        source_exam_profile = None
        if selected_source_exam is not None and selected_source_exam.questions:
            source_exam_profile = SourceExamProfile(
                source_exam_id=selected_source_exam.source_exam_id,
                title=selected_source_exam.title,
                questions=tuple(
                    SourceExamQuestionProfile(
                        question_number=question.question_number,
                        choice_count=len(question.options),
                        topic=self._domain(question.topic),
                        learning_objective=question.learning_objective or question.topic,
                        question_type=MockExamGenerationService.classify_source_question(
                            question
                        ).value,
                        difficulty=self._difficulty(question.difficulty),
                    )
                    for question in sorted(
                        selected_source_exam.questions,
                        key=lambda item: item.question_number,
                    )
                ),
            )
        return PackageBuildSnapshot(
            package_id=package.package_id,
            version=version.version,
            title=package.title,
            created_at=version.created_at,
            configuration=version.configuration,
            curriculum=curriculum,
            mock_exams=exams,
            source_exam_profile=source_exam_profile,
            model_metadata=version.model_metadata | self._model_metadata(exams),
            prompt_versions=prompt_versions,
        )

    @staticmethod
    def _materials_requiring_card_repair(
        curriculum: CurriculumSnapshot,
        expected_cards: int,
    ) -> set[str]:
        repair_ids = {
            book.material_id
            for book in curriculum.books
            if not book.concepts
            or any(len(concept.flashcards) != expected_cards for concept in book.concepts)
        }
        if curriculum.rejected_flashcard_count:
            repair_ids.update(book.material_id for book in curriculum.books)
        return repair_ids

    def _offline_exam(
        self,
        exam_number: int,
        session: StoredMockExamSession,
        *,
        timer_minutes: int,
    ) -> OfflineMockExam:
        keys = {key.question_id: key for key in session.answer_keys}
        questions = tuple(
            self._offline_question(number, question, keys.get(question.question_id))
            for number, question in enumerate(session.exam.questions, start=1)
        )
        return OfflineMockExam(
            exam_id=session.exam.exam_id,
            title=session.exam.blueprint.title or f"Practice Exam {exam_number}",
            timer_minutes=timer_minutes,
            questions=questions,
        )

    def _offline_question(
        self,
        question_number: int,
        question: QuizQuestion,
        key: StoredQuestionKey | None,
    ) -> OfflineExamQuestion:
        if key is None:
            raise PackageBuildError(f"Question {question.question_id} has no persisted answer key.")
        options = question.options or question.answer_choices_json
        if not 2 <= len(options) <= 8:
            raise PackageBuildError(
                f"Question {question.question_id} must contain two to eight answer choices."
            )
        correct_index = self._correct_index(question, key)
        explanation = question.explanation or question.rationale
        if not explanation:
            raise PackageBuildError(f"Question {question.question_id} has no explanation.")
        source_page = key.source_page or question.source_page
        citations = key.citations or question.citations
        if citations:
            source_reference = citations[0].citation_label
        elif source_page is not None:
            source_reference = f"{question.section_title}, page {source_page}"
        else:
            raise PackageBuildError(f"Question {question.question_id} has no source reference.")
        quality = question.quality_validation
        if quality is None:
            raise PackageBuildError(
                f"Question {question.question_id} has no PyTorch quality provenance."
            )
        domain = self._domain(question.section_title)
        return OfflineExamQuestion(
            question_id=question.question_id,
            question_number=question_number,
            domain=domain,
            subtopic=question.concept,
            learning_objective=question.concept,
            question_type=self._question_type(question),
            difficulty=self._difficulty(question.difficulty),
            prompt=question.prompt,
            choices=tuple(option.text for option in options),
            correct_choice_index=correct_index,
            explanation=explanation,
            source_reference=source_reference,
            source_excerpt=key.source_evidence or question.source_evidence,
            quality_score=quality.score,
            quality_confidence=quality.confidence,
            quality_label=quality.label.value,
            quality_accepted=quality.accepted_for_delivery,
            quality_model_version=quality.model_version,
            quality_model_source=quality.model_source,
        )

    @staticmethod
    def _correct_index(question: QuizQuestion, key: StoredQuestionKey) -> int:
        options = question.options or question.answer_choices_json
        for index, option in enumerate(options):
            if key.correct_option_id and option.option_id == key.correct_option_id:
                return index
            if option.text.strip() == key.correct_answer.strip():
                return index
        raise PackageBuildError(
            f"Question {question.question_id} answer key does not match a choice."
        )

    @staticmethod
    def _domain(value: str) -> str:
        normalized = value.casefold()
        for domain in FRM_PART_I_POLICY.domain_weights:
            if domain.casefold() in normalized or normalized in domain.casefold():
                return domain
        return value

    @staticmethod
    def _question_type(question: QuizQuestion) -> str:
        if question.frm_question_type is not None:
            return question.frm_question_type.value
        if question.question_style == QuestionStyle.CALCULATION:
            return ExamQuestionCategory.CALCULATION.value
        if question.question_style in {QuestionStyle.SCENARIO, QuestionStyle.CASE_BASED}:
            return ExamQuestionCategory.SCENARIO.value
        text = f"{question.concept} {question.section_title} {question.prompt}".casefold()
        if any(term in text for term in ("ethic", "professional conduct", "code of conduct")):
            return ExamQuestionCategory.ETHICS.value
        if any(term in text for term in ("model limitation", "model output", "regression output")):
            return ExamQuestionCategory.MODEL_INTERPRETATION.value
        return ExamQuestionCategory.APPLIED_CONCEPTUAL.value

    @staticmethod
    def _difficulty(value: float) -> str:
        if value <= 0.3:
            return "Foundational"
        if value >= 0.75:
            return "Difficult"
        return "Standard exam-level"

    def _source_fingerprint(self, configuration: PackageCreateRequest) -> str:
        records = self.material_store.list_records_by_course(configuration.course_id)
        record_by_id = {record.material_id: record for record in records}
        selected_ids = configuration.material_ids or tuple(
            sorted(record_by_id)
        )
        parts = [
            f"{material_id}:{record_by_id[material_id].content_hash or 'unknown'}"
            for material_id in selected_ids
            if material_id in record_by_id
        ]
        if configuration.source_exam_id is not None:
            parts.append(f"source-exam:{configuration.source_exam_id}")
        parts.extend(f"generated-exam:{exam_id}" for exam_id in configuration.generated_exam_ids)
        return "|".join(parts) or "sources-pending"

    @staticmethod
    def _model_metadata(exams: tuple[OfflineMockExam, ...]) -> dict[str, str]:
        questions = tuple(question for exam in exams for question in exam.questions)
        model_versions = sorted({question.quality_model_version for question in questions})
        model_sources = sorted({question.quality_model_source for question in questions})
        scores = [question.quality_score for question in questions]
        metadata = {
            "question_quality_model_versions": ",".join(model_versions),
            "question_quality_model_sources": ",".join(model_sources),
        }
        if scores:
            metadata["question_quality_min_score"] = f"{min(scores):.4f}"
        return metadata

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
