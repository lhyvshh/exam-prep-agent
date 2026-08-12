from exam_prep.ingestion.pipeline import IngestionPipeline
from exam_prep.repositories.local.material_store import LocalMaterialStore
from exam_prep.schemas.materials import FormulaAsset, SourceLocator, SourceSection


class _DebugReportParser:
    def parse(
        self,
        *,
        material_id: str,
        course_id: str,
        module_id: str | None,
        file_name: str,
        content_type: str,
        data: bytes,
    ) -> list[SourceSection]:
        return [
            _section(
                material_id=material_id,
                course_id=course_id,
                module_id=module_id,
                file_name=file_name,
                content_type=content_type,
                index=1,
                title="Study Session 2 · Reading 5: Module 5.1: Modern Portfolio Theory and the Capital Market Line",
                text=(
                    "LEARNING OBJECTIVES\n"
                    "LO 5.a: Explain Modern Portfolio Theory and the Markowitz efficient frontier.\n"
                    "KEY CONCEPTS\n"
                    "LO 5.a\n"
                    "Modern Portfolio Theory explains efficient combinations of risky assets."
                ),
                page_number=71,
                page_end=73,
            ),
            _section(
                material_id=material_id,
                course_id=course_id,
                module_id=module_id,
                file_name=file_name,
                content_type=content_type,
                index=2,
                title="Study Session 3 · Reading 11: Module 11.1: GARP Code of Conduct",
                text=(
                    "LEARNING OBJECTIVES\n"
                    "LO 11.a: Describe the responsibility of GARP members.\n"
                    "LO 11.b: Describe the potential consequences of violating the GARP Code of Conduct."
                ),
                page_number=153,
                page_end=158,
            ),
            _section(
                material_id=material_id,
                course_id=course_id,
                module_id=module_id,
                file_name=file_name,
                content_type=content_type,
                index=3,
                title="Formulas",
                text="FORMULAS\nReading 5\ncapital market line",
                page_number=160,
                page_end=160,
                formula_assets=[
                    FormulaAsset(
                        source_page=160,
                        path=f"formula-crop://{material_id}/page-160-full-1.png",
                        label="Formula page crop",
                        reading_number=5,
                        confidence=0.8,
                    )
                ],
            ),
        ]


def test_ingestion_persists_parse_debug_report_after_processing(tmp_path) -> None:
    store = LocalMaterialStore(tmp_path)
    pipeline = IngestionPipeline(store=store, parser=_DebugReportParser())

    record = pipeline.ingest(
        course_id="course-frm",
        file_name="FRM 2025 Part 1 KAPLAN Book 1.PDF",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    debug_report = record.parse_debug_report
    assert debug_report is not None
    assert debug_report["book"] == "FRM 2025 Part 1 KAPLAN Book 1.PDF"
    assert debug_report["readingsDetected"] == 2
    assert debug_report["readingNumbersDetected"] == [5, 11]
    assert debug_report["modulesDetected"] == 2
    assert debug_report["moduleNumbersDetected"] == ["5.1", "11.1"]
    assert debug_report["missingExpectedReadings"] == []
    assert debug_report["missingExpectedModules"] == []
    assert debug_report["missingExpectedLOs"] == []
    assert debug_report["formulaPagesDetected"] == [160]
    assert isinstance(debug_report["cardsGenerated"], int)
    assert isinstance(debug_report["cardsRejectedByQualityGate"], int)
    assert isinstance(debug_report["sampleRejectedReasons"], list)

    persisted = store.get_record(record.material_id)
    assert persisted is not None
    assert persisted.parse_debug_report == debug_report


def _section(
    *,
    material_id: str,
    course_id: str,
    module_id: str | None,
    file_name: str,
    content_type: str,
    index: int,
    title: str,
    text: str,
    page_number: int,
    page_end: int,
    formula_assets: list[FormulaAsset] | None = None,
) -> SourceSection:
    return SourceSection(
        source_id=f"{material_id}-section-{index}",
        material_id=material_id,
        course_id=course_id,
        module_id=module_id,
        file_name=file_name,
        content_type=content_type,
        section_title=title,
        text=text,
        page_end=page_end,
        formula_assets=formula_assets or [],
        locator=SourceLocator(section_index=index, page_number=page_number),
        citation_label=f"{file_name} page {page_number}",
    )
