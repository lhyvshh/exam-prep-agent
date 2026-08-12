from typing import Protocol
from pathlib import Path

from exam_prep.schemas.materials import MaterialRecord, MaterialStudyDocument, ParsedMaterialDocument


class MaterialStore(Protocol):
    def save_record(self, record: MaterialRecord) -> MaterialRecord:
        ...

    def save_parsed_document(self, document: ParsedMaterialDocument, raw_bytes: bytes) -> None:
        ...

    def save_raw_material(self, record: MaterialRecord, raw_bytes: bytes) -> MaterialRecord:
        ...

    def get_raw_material(self, material_id: str) -> bytes | None:
        ...

    def get_record(self, material_id: str) -> MaterialRecord | None:
        ...

    def get_parsed_document(self, material_id: str) -> ParsedMaterialDocument | None:
        ...

    def save_study_document(self, document: MaterialStudyDocument) -> None:
        ...

    def get_study_document(self, material_id: str) -> MaterialStudyDocument | None:
        ...

    def get_formula_crop_asset_path(self, material_id: str, asset_name: str) -> Path | None:
        ...

    def clear_material_processing_artifacts(self, material_id: str) -> None:
        ...

    def list_records_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[MaterialRecord]:
        ...

    def list_parsed_documents_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[ParsedMaterialDocument]:
        ...

    def delete_material(self, material_id: str) -> bool:
        ...
