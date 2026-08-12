import argparse
import json
import sys
from collections.abc import Sequence

from exam_prep.core.config import Settings
from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.repositories.local.exam_store import LocalExamStore
from exam_prep.repositories.local.material_store import LocalMaterialStore
from exam_prep.repositories.sqlite.material_catalog import SQLiteMaterialCatalog
from ..repositories.sqlite.package_store import SQLitePackageStore

from .assembler import PackageAssemblyError
from .models import PackageCreateRequest
from .service import PackageService, PackageServiceError


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    service = _service(Settings())
    try:
        if args.command == "create":
            record = service.create(
                PackageCreateRequest(
                    course_id=args.course_id,
                    title=args.title,
                    mock_exam_count=args.mock_exam_count,
                    questions_per_exam=args.questions_per_exam,
                    timer_minutes=args.timer_minutes,
                    include_formula_review=args.include_formula_review,
                )
            )
            _write_json(record.model_dump(mode="json"))
            return 0
        if args.command == "list":
            records = service.list_packages(args.course_id)
            _write_json({"packages": [record.model_dump(mode="json") for record in records]})
            return 0
        if args.command == "validate":
            report = service.validate(args.package_id)
            _write_json(report.model_dump(mode="json"))
            return 0 if report.passed else 3
        if args.command == "export":
            result = service.build(args.package_id)
            _write_json(
                {
                    "package_id": result.manifest.package_id,
                    "version": result.manifest.version,
                    "zip_path": str(result.zip_path),
                    "manifest": result.manifest.model_dump(mode="json"),
                }
            )
            return 0
    except (PackageServiceError, PackageAssemblyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    parser.error("Unknown command.")
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="study-package",
        description="Create and export validated offline exam-prep packages.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Create package metadata.")
    create.add_argument("--course-id", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--mock-exam-count", type=int, default=3)
    create.add_argument("--questions-per-exam", type=int, default=100)
    create.add_argument("--timer-minutes", type=int, default=240)
    create.add_argument(
        "--include-formula-review",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    list_command = commands.add_parser("list", help="List course packages.")
    list_command.add_argument("--course-id", required=True)

    validate = commands.add_parser("validate", help="Validate a package snapshot.")
    validate.add_argument("--package-id", required=True)

    export = commands.add_parser("export", help="Build and export a validated package.")
    export.add_argument("--package-id", required=True)
    return parser


def _service(settings: Settings) -> PackageService:
    database = SQLiteDatabase(settings.sqlite_path)
    database.initialize()
    catalog = SQLiteMaterialCatalog(
        database,
        parse_section_token_limit=settings.max_section_tokens_for_parse,
    )
    material_store = LocalMaterialStore(settings.material_storage_path, catalog=catalog)
    return PackageService(
        package_store=SQLitePackageStore(database),
        material_store=material_store,
        exam_store=LocalExamStore(settings.material_storage_path),
        storage_root=settings.material_storage_path,
    )


def _write_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
