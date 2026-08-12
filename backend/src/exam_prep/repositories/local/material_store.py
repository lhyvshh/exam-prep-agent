from pathlib import Path
import shutil

from exam_prep.repositories.material_catalog import MaterialCatalog
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.schemas.materials import MaterialRecord, MaterialStudyDocument, ParsedMaterialDocument


class LocalMaterialStore(MaterialStore):
    def __init__(self, base_path: Path, catalog: MaterialCatalog | None = None) -> None:
        self.base_path = base_path
        self.catalog = catalog
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_record(self, record: MaterialRecord) -> MaterialRecord:
        material_dir = self._material_dir(record.material_id)
        material_dir.mkdir(parents=True, exist_ok=True)
        (material_dir / "record.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")
        if self.catalog is not None:
            self.catalog.upsert_record(record)
        return record

    def save_parsed_document(self, document: ParsedMaterialDocument, raw_bytes: bytes) -> None:
        material_dir = self._material_dir(document.record.material_id)
        material_dir.mkdir(parents=True, exist_ok=True)
        source_path = self._source_path(document.record)
        raw_text_path = material_dir / "raw_text.txt"
        if raw_bytes:
            source_path.write_bytes(raw_bytes)
        raw_text_path.write_text(
            "\n\n".join(section.text for section in document.sections).strip(),
            encoding="utf-8",
        )
        if document.record.file_path != str(source_path):
            document = document.model_copy(
                update={
                    "record": document.record.model_copy(
                        update={
                            "file_path": str(source_path),
                            "raw_text_path": str(raw_text_path),
                        }
                    )
                }
            )
        elif document.record.raw_text_path != str(raw_text_path):
            document = document.model_copy(
                update={
                    "record": document.record.model_copy(
                        update={"raw_text_path": str(raw_text_path)}
                    )
                }
            )
        (material_dir / "parsed.json").write_text(
            document.model_dump_json(indent=2),
            encoding="utf-8",
        )
        self.save_record(document.record)
        if self.catalog is not None:
            self.catalog.replace_sections(
                document.record.material_id,
                document.record.course_id,
                document.record.module_id,
                document.sections,
            )
            self.catalog.replace_chunks(document)

    def save_raw_material(self, record: MaterialRecord, raw_bytes: bytes) -> MaterialRecord:
        material_dir = self._material_dir(record.material_id)
        material_dir.mkdir(parents=True, exist_ok=True)
        source_path = self._source_path(record)
        source_path.write_bytes(raw_bytes)
        saved_record = record.model_copy(update={"file_path": str(source_path)})
        self.save_record(saved_record)
        return saved_record

    def get_raw_material(self, material_id: str) -> bytes | None:
        record = self.get_record(material_id)
        if record is None:
            return None
        source_path = Path(record.file_path) if record.file_path else self._source_path(record)
        if not source_path.exists():
            return None
        return source_path.read_bytes()

    def get_record(self, material_id: str) -> MaterialRecord | None:
        if self.catalog is not None:
            catalog_record = self.catalog.get_record(material_id)
            if catalog_record is not None:
                return catalog_record
        record_path = self._material_dir(material_id) / "record.json"
        if not record_path.exists():
            return None
        return MaterialRecord.model_validate_json(record_path.read_text(encoding="utf-8"))

    def get_parsed_document(self, material_id: str) -> ParsedMaterialDocument | None:
        parsed_path = self._material_dir(material_id) / "parsed.json"
        if not parsed_path.exists():
            return None
        return ParsedMaterialDocument.model_validate_json(parsed_path.read_text(encoding="utf-8"))

    def save_study_document(self, document: MaterialStudyDocument) -> None:
        study_path = self._material_dir(document.material_id) / "study.json"
        study_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
        if self.catalog is not None:
            self.catalog.replace_study_assets(
                document,
                self.get_parsed_document(document.material_id),
            )

    def get_study_document(self, material_id: str) -> MaterialStudyDocument | None:
        study_path = self._material_dir(material_id) / "study.json"
        if not study_path.exists():
            return None
        return MaterialStudyDocument.model_validate_json(study_path.read_text(encoding="utf-8"))

    def get_formula_crop_asset_path(self, material_id: str, asset_name: str) -> Path | None:
        safe_name = Path(asset_name).name
        if not safe_name or safe_name != asset_name:
            return None
        asset_path = self._material_dir(material_id) / "formula-crops" / safe_name
        if not asset_path.exists() or not asset_path.is_file():
            return None
        return asset_path

    def clear_material_processing_artifacts(self, material_id: str) -> None:
        if self.catalog is not None:
            self.catalog.clear_material_processing_artifacts(material_id)

        material_dir = self._material_dir(material_id)
        if not material_dir.exists():
            return

        for artifact_name in ("raw_text.txt", "parsed.json", "study.json"):
            artifact_path = material_dir / artifact_name
            if artifact_path.exists():
                artifact_path.unlink()

        derived_asset_dirs = (
            "formula-crops",
            "formula_crops",
            "formula-assets",
            "formula_assets",
            "crops",
        )
        for asset_dir_name in derived_asset_dirs:
            asset_dir = material_dir / asset_dir_name
            if asset_dir.exists() and asset_dir.is_dir():
                shutil.rmtree(asset_dir)

        for asset_path in material_dir.glob("formula-crop*"):
            if asset_path.is_file():
                asset_path.unlink()

    def list_records_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[MaterialRecord]:
        if self.catalog is not None:
            return self.catalog.list_records_by_course(course_id, module_id)
        records: list[MaterialRecord] = []
        for material_dir in self.base_path.iterdir():
            if not material_dir.is_dir() or material_dir.name.startswith("_"):
                continue
            record = self.get_record(material_dir.name)
            if (
                record is not None
                and record.course_id == course_id
                and (module_id is None or record.module_id == module_id)
            ):
                records.append(record)
        return sorted(records, key=lambda record: record.file_name)

    def list_parsed_documents_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[ParsedMaterialDocument]:
        documents: list[ParsedMaterialDocument] = []
        for material_dir in self.base_path.iterdir():
            if not material_dir.is_dir() or material_dir.name.startswith("_"):
                continue
            document = self.get_parsed_document(material_dir.name)
            if (
                document is not None
                and document.record.course_id == course_id
                and (module_id is None or document.record.module_id == module_id)
            ):
                documents.append(document)
        return sorted(documents, key=lambda document: document.record.file_name)

    def delete_material(self, material_id: str) -> bool:
        material_dir = self._material_dir(material_id)
        if not material_dir.exists():
            return False
        if self.catalog is not None:
            self.catalog.delete_material(material_id)
        shutil.rmtree(material_dir)
        return True

    def _material_dir(self, material_id: str) -> Path:
        return self.base_path / material_id

    def _source_path(self, record: MaterialRecord) -> Path:
        extension = Path(record.file_name).suffix or ".bin"
        return self._material_dir(record.material_id) / f"source{extension}"
