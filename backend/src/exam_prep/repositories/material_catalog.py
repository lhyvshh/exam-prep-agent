from typing import Protocol

from exam_prep.schemas.materials import (
    MaterialRecord,
    MaterialSectionSummary,
    MaterialStudyDocument,
    ParsedMaterialDocument,
    SourceSection,
    StructuredConcept,
    StructuredMaterialChunk,
    StructuredMaterialSection,
)


class MaterialCatalog(Protocol):
    def list_course_ids(self) -> list[str]:
        ...

    def upsert_record(self, record: MaterialRecord) -> None:
        ...

    def get_record(self, material_id: str) -> MaterialRecord | None:
        ...

    def list_records(
        self,
        course_id: str | None = None,
        module_id: str | None = None,
    ) -> list[MaterialRecord]:
        ...

    def list_records_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[MaterialRecord]:
        ...

    def replace_sections(
        self,
        material_id: str,
        course_id: str,
        module_id: str | None,
        sections: list[SourceSection],
    ) -> None:
        ...

    def replace_chunks(self, document: ParsedMaterialDocument) -> None:
        ...

    def replace_study_assets(
        self,
        study_document: MaterialStudyDocument,
        parsed_document: ParsedMaterialDocument | None = None,
    ) -> None:
        ...

    def clear_material_processing_artifacts(self, material_id: str) -> None:
        ...

    def list_structured_sections(self, material_id: str) -> list[StructuredMaterialSection]:
        ...

    def get_structured_section(self, section_id: str) -> StructuredMaterialSection | None:
        ...

    def list_chunks_by_section(self, section_id: str) -> list[StructuredMaterialChunk]:
        ...

    def get_concept(self, concept_id: str) -> StructuredConcept | None:
        ...

    def list_sections_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[MaterialSectionSummary]:
        ...

    def delete_material(self, material_id: str) -> None:
        ...
