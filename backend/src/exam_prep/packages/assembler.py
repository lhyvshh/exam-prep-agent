import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from .frm_policy import FRM_PART_I_POLICY
from .models import (
    ExamBlueprintMode,
    OfflineFlashcard,
    OfflineFormula,
    PackageContentCounts,
    PackageFile,
    PackageFileKind,
    PackageKind,
    PackageManifest,
    PackageValidationReport,
)
from .rendering import (
    BlueprintFileInput,
    FlashcardFileInput,
    FormulaFileInput,
    MockExamFileInput,
    OfflineRenderer,
)
from .validation import PackageBuildSnapshot, PackageValidator


class PackageAssemblyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PackageAssemblyResult:
    manifest: PackageManifest
    output_dir: Path
    zip_path: Path
    files: tuple[PackageFile, ...]


class PackageAssembler:
    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root
        self.renderer = OfflineRenderer()
        self.validator = PackageValidator()

    def assemble(self, snapshot: PackageBuildSnapshot) -> PackageAssemblyResult:
        report = self.validator.validate(snapshot)
        if not report.is_complete:
            codes = ", ".join(finding.code for finding in report.hard_failures)
            raise PackageAssemblyError(f"Package failed hard validation: {codes}")

        package_root = self.storage_root / "_packages" / snapshot.package_id
        output_dir = package_root / f"v{snapshot.version}"
        if output_dir.exists():
            raise PackageAssemblyError(f"Package version already exists: {output_dir}")
        temporary_dir = package_root / f".v{snapshot.version}-{uuid4().hex}.tmp"
        temporary_dir.mkdir(parents=True)

        try:
            files = self._write_rendered_files(temporary_dir, snapshot)
            manifest = self._manifest(snapshot, report, files)
            zip_name = f"{self._file_stem(snapshot.title)}.zip"
            temporary_zip = temporary_dir / zip_name
            self._write_zip(temporary_dir, temporary_zip)
            zip_file = self._file_record(
                snapshot,
                PackageFileKind.ZIP,
                zip_name,
                "application/zip",
                temporary_zip.read_bytes(),
                len(files),
            )
            temporary_dir.replace(output_dir)
        except Exception:
            if temporary_dir.exists():
                shutil.rmtree(temporary_dir)
            raise

        return PackageAssemblyResult(
            manifest=manifest,
            output_dir=output_dir,
            zip_path=output_dir / zip_name,
            files=(*files, zip_file),
        )

    def _write_rendered_files(
        self,
        output_dir: Path,
        snapshot: PackageBuildSnapshot,
    ) -> tuple[PackageFile, ...]:
        files: list[PackageFile] = []
        match snapshot.configuration.package_kind:
            case PackageKind.COMPLETE:
                include_flashcards = True
                include_exam = True
            case PackageKind.STUDY_CARDS:
                include_flashcards = True
                include_exam = False
            case PackageKind.MOCK_EXAM:
                include_flashcards = False
                include_exam = True
            case unreachable:
                assert_never(unreachable)

        if include_flashcards:
            for index, book in enumerate(snapshot.curriculum.books, start=1):
                cards: tuple[OfflineFlashcard, ...] = tuple(
                    card for concept in book.concepts for card in concept.flashcards
                )
                file_name = f"{index:02d}-{self._file_stem(book.title)}-Flashcards.html"
                html = self.renderer.render_flashcards(
                    FlashcardFileInput(
                        package_id=snapshot.package_id,
                        file_id=f"flashcards-{book.material_id}",
                        version=snapshot.version,
                        title=f"{book.title} Flashcards",
                        cards=cards,
                    )
                )
                files.append(
                    self._write_file(
                        output_dir,
                        snapshot,
                        PackageFileKind.FLASHCARDS,
                        file_name,
                        "text/html",
                        html.encode(),
                        len(cards),
                    )
                )

        if include_exam:
            for index, exam in enumerate(snapshot.mock_exams, start=1):
                file_name = f"Mock-Exam-{index}.html"
                html = self.renderer.render_mock_exam(
                    MockExamFileInput(
                        package_id=snapshot.package_id,
                        file_id=f"mock-exam-{index}",
                        version=snapshot.version,
                        exam=exam,
                    )
                )
                files.append(
                    self._write_file(
                        output_dir,
                        snapshot,
                        PackageFileKind.MOCK_EXAM,
                        file_name,
                        "text/html",
                        html.encode(),
                        len(exam.questions),
                    )
                )

        formulas: tuple[OfflineFormula, ...] = tuple(
            formula for book in snapshot.curriculum.books for formula in book.formulas
        )
        if include_flashcards and snapshot.configuration.include_formula_review and formulas:
            html = self.renderer.render_formula_review(
                FormulaFileInput(
                    package_id=snapshot.package_id,
                    file_id="formula-review",
                    version=snapshot.version,
                    title=f"{snapshot.configuration.exam_name} Formula Review",
                    formulas=formulas,
                )
            )
            files.append(
                self._write_file(
                    output_dir,
                    snapshot,
                    PackageFileKind.FORMULA_REVIEW,
                    "Formula-Review.html",
                    "text/html",
                    html.encode(),
                    len(formulas),
                )
            )

        if (
            include_exam
            and snapshot.configuration.exam_blueprint_mode == ExamBlueprintMode.FRM_PART_I
        ):
            blueprint = BlueprintFileInput(
                package_id=snapshot.package_id,
                file_id="exam-blueprint",
                version=snapshot.version,
                title="FRM Part I Exam Blueprint",
                domain_weights=dict(FRM_PART_I_POLICY.domain_weights),
                exam_domain_counts=tuple(dict(item) for item in FRM_PART_I_POLICY.exam_domain_counts),
                question_type_counts=dict(FRM_PART_I_POLICY.question_type_counts),
                difficulty_counts=tuple(dict(item) for item in FRM_PART_I_POLICY.difficulty_counts),
            )
            files.append(
                self._write_file(
                    output_dir,
                    snapshot,
                    PackageFileKind.EXAM_BLUEPRINT,
                    "Exam-Blueprint.html",
                    "text/html",
                    self.renderer.render_blueprint(blueprint).encode(),
                    3,
                )
            )
        return tuple(files)

    def _manifest(
        self,
        snapshot: PackageBuildSnapshot,
        report: PackageValidationReport,
        files: tuple[PackageFile, ...],
    ) -> PackageManifest:
        concepts = tuple(
            concept for book in snapshot.curriculum.books for concept in book.concepts
        )
        formulas = tuple(formula for book in snapshot.curriculum.books for formula in book.formulas)
        questions = tuple(question for exam in snapshot.mock_exams for question in exam.questions)
        return PackageManifest(
            package_id=snapshot.package_id,
            version=snapshot.version,
            title=snapshot.title,
            created_at=snapshot.created_at,
            generator_version="1",
            content_counts=PackageContentCounts(
                books=len(snapshot.curriculum.books),
                concepts=len(concepts),
                flashcards=sum(len(concept.flashcards) for concept in concepts),
                formulas=len(formulas),
                mock_exams=len(snapshot.mock_exams),
                exam_questions=len(questions),
            ),
            files=files,
            validation=report,
            source_document_versions={
                book.material_id: book.content_hash or "unknown"
                for book in snapshot.curriculum.books
            },
            model_metadata=snapshot.model_metadata,
            prompt_versions=snapshot.prompt_versions,
        )

    def _write_file(
        self,
        output_dir: Path,
        snapshot: PackageBuildSnapshot,
        kind: PackageFileKind,
        file_name: str,
        media_type: str,
        content: bytes,
        content_count: int,
    ) -> PackageFile:
        if Path(file_name).name != file_name or file_name in {".", ".."}:
            raise PackageAssemblyError(f"Unsafe package file name: {file_name}")
        (output_dir / file_name).write_bytes(content)
        return self._file_record(
            snapshot,
            kind,
            file_name,
            media_type,
            content,
            content_count,
        )

    @staticmethod
    def _file_record(
        snapshot: PackageBuildSnapshot,
        kind: PackageFileKind,
        file_name: str,
        media_type: str,
        content: bytes,
        content_count: int,
    ) -> PackageFile:
        return PackageFile(
            file_id=f"{kind.value}-{hashlib.sha256(file_name.encode()).hexdigest()[:12]}",
            package_id=snapshot.package_id,
            version=snapshot.version,
            kind=kind,
            file_name=file_name,
            media_type=media_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            content_count=content_count,
            artifact_path=f"_packages/{snapshot.package_id}/v{snapshot.version}/{file_name}",
        )

    @staticmethod
    def _write_zip(output_dir: Path, zip_path: Path) -> None:
        with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
            for file_path in sorted(output_dir.iterdir()):
                if file_path == zip_path or not file_path.is_file():
                    continue
                if file_path.name in {".", ".."} or Path(file_path.name).name != file_path.name:
                    raise PackageAssemblyError(f"Unsafe ZIP entry: {file_path.name}")
                archive.write(file_path, file_path.name)

    @staticmethod
    def _file_stem(value: str) -> str:
        stem = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
        return stem or "Study-Package"
