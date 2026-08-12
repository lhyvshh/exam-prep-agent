from pathlib import Path

import pytest

from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.packages.assembler import PackageAssembler, PackageAssemblyResult
from exam_prep.packages.curriculum import (
    CurriculumBookSnapshot,
    CurriculumConceptSnapshot,
    CurriculumSnapshot,
)
from exam_prep.packages.models import (
    OfflineFlashcard,
    PackageContentCounts,
    PackageCreateRequest,
    PackageFile,
    PackageFileKind,
    PackageGenerationJob,
    PackageJobStatus,
    PackageKind,
    PackageManifest,
    PackageRecord,
    PackageStatus,
    PackageValidationReport,
    PackageVersion,
)
from exam_prep.packages.jobs import PackageJobRunner
from exam_prep.packages.service import PackageBuildError, PackageService
from exam_prep.packages.validation import PackageBuildSnapshot
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.sqlite.package_store import SQLitePackageStore
from exam_prep.schemas.exam import MockExamSourceBank, MockExamSourceExam, StoredMockExamSession
from exam_prep.schemas.materials import MaterialRecord, MaterialStudyDocument, ParsedMaterialDocument


class UnusedMaterialStore:
    def save_record(self, record: MaterialRecord) -> MaterialRecord:
        raise AssertionError("material store is not used in this test")

    def save_parsed_document(self, document: ParsedMaterialDocument, raw_bytes: bytes) -> None:
        raise AssertionError("material store is not used in this test")

    def save_raw_material(self, record: MaterialRecord, raw_bytes: bytes) -> MaterialRecord:
        raise AssertionError("material store is not used in this test")

    def get_raw_material(self, material_id: str) -> bytes | None:
        raise AssertionError("material store is not used in this test")

    def get_record(self, material_id: str) -> MaterialRecord | None:
        raise AssertionError("material store is not used in this test")

    def get_parsed_document(self, material_id: str) -> ParsedMaterialDocument | None:
        raise AssertionError("material store is not used in this test")

    def save_study_document(self, document: MaterialStudyDocument) -> None:
        raise AssertionError("material store is not used in this test")

    def get_study_document(self, material_id: str) -> MaterialStudyDocument | None:
        raise AssertionError("material store is not used in this test")

    def get_formula_crop_asset_path(self, material_id: str, asset_name: str) -> Path | None:
        raise AssertionError("material store is not used in this test")

    def clear_material_processing_artifacts(self, material_id: str) -> None:
        raise AssertionError("material store is not used in this test")

    def list_records_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[MaterialRecord]:
        return [
            MaterialRecord(
                material_id=f"material-{index}",
                course_id=course_id,
                file_name=f"Book-{index}.pdf",
                content_type="application/pdf",
                content_hash=f"book-hash-{index}",
            )
            for index in range(1, 5)
        ]

    def list_parsed_documents_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[ParsedMaterialDocument]:
        raise AssertionError("material store is not used in this test")

    def delete_material(self, material_id: str) -> bool:
        raise AssertionError("material store is not used in this test")


class UnusedExamStore:
    def save_exam_session(self, session: StoredMockExamSession) -> None:
        raise AssertionError("exam store is not used in this test")

    def get_exam_session(self, exam_id: str) -> StoredMockExamSession | None:
        raise AssertionError("exam store is not used in this test")

    def list_exam_sessions_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[StoredMockExamSession]:
        raise AssertionError("exam store is not used in this test")

    def save_source_bank(self, bank: MockExamSourceBank) -> None:
        raise AssertionError("exam store is not used in this test")

    def get_source_bank(self, bank_id: str) -> MockExamSourceBank | None:
        raise AssertionError("exam store is not used in this test")

    def get_source_exam(self, source_exam_id: str) -> MockExamSourceExam | None:
        raise AssertionError("exam store is not used in this test")

    def list_source_banks_by_course(self, course_id: str) -> list[MockExamSourceBank]:
        raise AssertionError("exam store is not used in this test")

    def list_generated_question_signatures(self, course_id: str) -> set[str]:
        raise AssertionError("exam store is not used in this test")


class SnapshotAssembler(PackageAssembler):
    def __init__(self, storage_root: Path) -> None:
        super().__init__(storage_root)

    def assemble(self, snapshot: PackageBuildSnapshot) -> PackageAssemblyResult:
        version = snapshot.version
        output_dir = self.storage_root / "_packages" / snapshot.package_id / f"v{version}"
        output_dir.mkdir(parents=True)
        zip_path = output_dir / "FRM-Part-I.zip"
        zip_path.write_bytes(b"zip")
        file = PackageFile(
            file_id="zip-file",
            package_id=snapshot.package_id,
            version=version,
            kind=PackageFileKind.ZIP,
            file_name="FRM-Part-I.zip",
            media_type="application/zip",
            size_bytes=3,
            sha256="a" * 64,
            content_count=1,
            artifact_path=f"_packages/{snapshot.package_id}/v{version}/FRM-Part-I.zip",
        )
        report = PackageValidationReport(
            package_id=snapshot.package_id,
            version=version,
            passed=True,
            created_at=snapshot.created_at,
        )
        manifest = PackageManifest(
            package_id=snapshot.package_id,
            version=version,
            title=snapshot.title,
            created_at=snapshot.created_at,
            generator_version="1",
            content_counts=PackageContentCounts(
                books=4,
                concepts=4,
                flashcards=40,
                formulas=0,
                mock_exams=3,
                exam_questions=300,
            ),
            files=(file,),
            validation=report,
            model_metadata={"question_quality_model_version": "torch-1"},
            prompt_versions={"mock_exam": "prompt-1"},
        )
        return PackageAssemblyResult(
            manifest=manifest,
            output_dir=output_dir,
            zip_path=zip_path,
            files=(file,),
        )


class FailingAssembler(PackageAssembler):
    def __init__(self, storage_root: Path) -> None:
        super().__init__(storage_root)

    def assemble(self, snapshot: PackageBuildSnapshot) -> PackageAssemblyResult:
        raise RuntimeError(f"renderer failed at {self.storage_root / 'secret' / 'artifact.html'}")


def _service(tmp_path: Path) -> tuple[PackageService, SQLitePackageStore]:
    database = SQLiteDatabase(tmp_path / "packages.sqlite3")
    database.initialize()
    store = SQLitePackageStore(database)
    material_store: MaterialStore = UnusedMaterialStore()
    exam_store: ExamStore = UnusedExamStore()
    service = PackageService(
        package_store=store,
        material_store=material_store,
        exam_store=exam_store,
        storage_root=tmp_path,
    )
    service.assembler = SnapshotAssembler(tmp_path)
    return service, store


def _completed_package() -> PackageRecord:
    return PackageRecord(
        package_id="package-1",
        course_id="course-1",
        title="FRM Part I Offline Package",
        exam_name="Financial Risk Manager",
        exam_part="Part I",
        status=PackageStatus.COMPLETE,
        active_version=1,
        created_at="2026-07-13T12:00:00Z",
        updated_at="2026-07-13T12:10:00Z",
    )


def _completed_version() -> PackageVersion:
    return PackageVersion(
        package_id="package-1",
        version=1,
        status=PackageStatus.COMPLETE,
        configuration=PackageCreateRequest(
            course_id="course-1",
            title="FRM Part I Offline Package",
        ),
        created_at="2026-07-13T12:00:00Z",
        completed_at="2026-07-13T12:10:00Z",
        source_fingerprint="source-fingerprint-1",
    )


def _draft_package() -> PackageRecord:
    return _completed_package().model_copy(
        update={
            "status": PackageStatus.DRAFT,
            "updated_at": "2026-07-13T12:00:00Z",
        }
    )


def _draft_version() -> PackageVersion:
    return _completed_version().model_copy(
        update={
            "status": PackageStatus.DRAFT,
            "completed_at": None,
        }
    )


def _snapshot_for_version(
    package: PackageRecord,
    version: PackageVersion,
) -> PackageBuildSnapshot:
    return PackageBuildSnapshot(
        package_id=package.package_id,
        version=version.version,
        title=package.title,
        created_at=version.created_at,
        configuration=version.configuration,
        curriculum=CurriculumSnapshot(course_id=package.course_id, books=()),
        mock_exams=(),
        model_metadata=version.model_metadata,
        prompt_versions=version.prompt_versions,
    )


def test_rebuild_of_completed_package_creates_incremented_active_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, store = _service(tmp_path)
    package = _completed_package()
    store.create_package(package)
    store.save_version(_completed_version())
    old_report = PackageValidationReport(
        package_id=package.package_id,
        version=1,
        passed=True,
        created_at="2026-07-13T12:11:00Z",
    )
    store.save_validation(old_report)
    monkeypatch.setattr(service, "_snapshot", _snapshot_for_version)

    result = service.build(package.package_id)

    rebuilt = store.get_package(package.package_id)
    assert rebuilt is not None
    assert rebuilt.active_version == 2
    assert store.get_version(package.package_id, 1) == _completed_version()
    version_two = store.get_version(package.package_id, 2)
    assert version_two is not None
    assert version_two.status == PackageStatus.COMPLETE
    assert store.get_validation(package.package_id, 1) == old_report
    assert store.get_validation(package.package_id, 2) == result.manifest.validation


def test_resolve_file_requires_complete_package_version_and_passing_validation(
    tmp_path: Path,
) -> None:
    service, store = _service(tmp_path)
    package = _completed_package().model_copy(update={"status": PackageStatus.BUILDING})
    version = _completed_version().model_copy(update={"status": PackageStatus.COMPLETE})
    file = PackageFile(
        file_id="zip-file",
        package_id=package.package_id,
        version=version.version,
        kind=PackageFileKind.ZIP,
        file_name="FRM-Part-I.zip",
        media_type="application/zip",
        size_bytes=3,
        sha256="a" * 64,
        artifact_path=f"_packages/{package.package_id}/v{version.version}/FRM-Part-I.zip",
    )
    assert file.artifact_path is not None
    artifact = tmp_path / file.artifact_path
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"zip")
    store.create_package(package)
    store.save_version(version)
    store.replace_files(package.package_id, version.version, [file])
    store.save_validation(
        PackageValidationReport(
            package_id=package.package_id,
            version=version.version,
            passed=True,
            created_at="2026-07-13T12:11:00Z",
        )
    )

    with pytest.raises(PackageBuildError, match="Package download is unavailable"):
        service.resolve_file(package.package_id, file.file_id)


def test_snapshot_repairs_underfilled_material_before_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _service(tmp_path)
    stale_document = MaterialStudyDocument(material_id="material-1", pipeline_version=1)
    repaired_document = MaterialStudyDocument(material_id="material-1", pipeline_version=2)
    monkeypatch.setattr(
        service.material_store,
        "get_study_document",
        lambda _: stale_document,
    )

    class RepairingStudyService:
        calls: list[tuple[str, bool]] = []

        def ensure_study_document(
            self,
            material_id: str,
            *,
            force: bool = False,
        ) -> MaterialStudyDocument:
            self.calls.append((material_id, force))
            return repaired_document

    repairer = RepairingStudyService()
    service.study_service = repairer  # type: ignore[assignment]

    class VersionedCurriculumBuilder:
        def build(
            self,
            *,
            course_id: str,
            materials: list[MaterialRecord],
            study_documents: list[MaterialStudyDocument],
        ) -> CurriculumSnapshot:
            card_count = 10 if study_documents[0].pipeline_version == 2 else 8
            cards = tuple(
                OfflineFlashcard(
                    card_id=f"card-{index}",
                    book_id="material-1",
                    learning_objective="LO 1.a",
                    concept_id="concept-1",
                    prompt=f"Prompt {index}",
                    answer=f"Answer {index}",
                    source_page=1,
                    source_reference="Book 1, page 1",
                )
                for index in range(card_count)
            )
            return CurriculumSnapshot(
                course_id=course_id,
                books=(
                    CurriculumBookSnapshot(
                        material_id=materials[0].material_id,
                        title="Book 1",
                        concepts=(
                            CurriculumConceptSnapshot(
                                concept_id="concept-1",
                                title="Concept 1",
                                learning_outcome="LO 1.a",
                                source_pages=(1,),
                                source_anchors=("section-1",),
                                flashcards=cards,
                            ),
                        ),
                        formulas=(),
                    ),
                ),
            )

    monkeypatch.setattr(
        "exam_prep.packages.service.CurriculumSnapshotBuilder",
        VersionedCurriculumBuilder,
    )
    configuration = PackageCreateRequest(
        course_id="course-1",
        title="Book 1 study cards",
        package_kind=PackageKind.STUDY_CARDS,
        material_ids=("material-1",),
        mock_exam_count=0,
        include_formula_review=False,
    )
    package = _draft_package().model_copy(
        update={"package_kind": PackageKind.STUDY_CARDS}
    )
    version = _draft_version().model_copy(update={"configuration": configuration})

    snapshot = service._snapshot(package, version)

    assert repairer.calls == [("material-1", True)]
    assert len(snapshot.curriculum.books[0].concepts[0].flashcards) == 10


def test_package_job_runner_sanitizes_errors_and_persists_failed_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, store = _service(tmp_path)
    package = _draft_package()
    version = _draft_version()
    store.create_package(package)
    store.save_version(version)
    service.assembler = FailingAssembler(tmp_path)
    monkeypatch.setattr(service, "_snapshot", _snapshot_for_version)
    job = PackageGenerationJob(
        job_id="job-1",
        package_id=package.package_id,
        version=version.version,
        status=PackageJobStatus.QUEUED,
        current_step="queued",
        created_at="2026-07-13T12:01:00Z",
        updated_at="2026-07-13T12:01:00Z",
    )
    runner = PackageJobRunner(service=service, job_store=store)

    runner._run(job)

    failed = store.get_job(job.job_id)
    assert failed is not None
    assert failed.error_message is not None
    assert str(tmp_path) not in failed.error_message
    assert failed.error_message == "renderer failed at [redacted-path]"
    with store.database.connect() as connection:
        row = connection.execute(
            """
            SELECT status, input_fingerprint, attempts, error_message
            FROM generation_job_steps
            WHERE job_id = ? AND step_name = ?
            """,
            (job.job_id, "assemble"),
        ).fetchone()
    assert row["status"] == PackageJobStatus.FAILED.value
    assert row["input_fingerprint"] == version.source_fingerprint
    assert row["attempts"] == 1
    assert row["error_message"] == failed.error_message
