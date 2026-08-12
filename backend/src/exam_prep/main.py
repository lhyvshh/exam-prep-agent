import logging
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from exam_prep.api.routes import activity, agents, analytics, config, courses, dashboard, exams, health, materials, ml, notifications, packages, quiz, retrieval, source, workflow
from exam_prep.core.config import DEFAULT_RUNTIME_ROOT, PROJECT_ROOT, Settings, get_settings
from exam_prep.core.logging import configure_logging
from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.repositories.local.exam_store import LocalExamStore
from exam_prep.repositories.local.material_store import LocalMaterialStore
from exam_prep.repositories.local.quiz_store import LocalQuizStore
from exam_prep.repositories.local.vector_store import LocalVectorStore
from exam_prep.repositories.sqlite.config_store import SQLiteConfigStore
from exam_prep.repositories.sqlite.agent_store import SQLiteAgentStore
from exam_prep.repositories.sqlite.activity_store import SQLiteActivityStore
from exam_prep.repositories.sqlite.analytics_store import SQLiteAnalyticsStore
from exam_prep.repositories.sqlite.course_store import SQLiteCourseStore
from exam_prep.repositories.sqlite.material_catalog import SQLiteMaterialCatalog
from exam_prep.repositories.sqlite.notification_store import SQLiteNotificationStore
from .repositories.sqlite.package_store import SQLitePackageStore
from exam_prep.repositories.sqlite.quiz_job_store import SQLiteQuizJobStore
from exam_prep.repositories.sqlite.workflow_store import SQLiteWorkflowStore
from exam_prep.services.quiz_job_runner import QuizJobRunner
from exam_prep.ingestion.pipeline import IngestionPipeline
from exam_prep.services.material_job_runner import MaterialJobRunner
from exam_prep.packages.jobs import PackageJobRunner
from exam_prep.packages.service import PackageService

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.debug)
    _bootstrap_runtime_storage(app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        app.state.material_job_runner.shutdown()
        app.state.package_job_runner.shutdown()
        app.state.quiz_job_runner.shutdown()
        app.state.llm_client_registry.close_all()

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        debug=app_settings.debug,
        lifespan=lifespan,
    )
    database = SQLiteDatabase(app_settings.sqlite_path)
    database.initialize()
    material_catalog = SQLiteMaterialCatalog(
        database,
        parse_section_token_limit=app_settings.max_section_tokens_for_parse,
    )

    app.state.settings = app_settings
    app.state.database = database
    app.state.config_store = SQLiteConfigStore(database)
    app.state.agent_store = SQLiteAgentStore(database)
    app.state.activity_store = SQLiteActivityStore(database)
    app.state.analytics_store = SQLiteAnalyticsStore(database)
    app.state.notification_store = SQLiteNotificationStore(database)
    app.state.package_store = SQLitePackageStore(database)
    app.state.llm_client_registry = LLMClientRegistry(app_settings)
    app.state.workflow_store = SQLiteWorkflowStore(database)
    app.state.course_store = SQLiteCourseStore(database)
    app.state.material_catalog = material_catalog
    app.state.material_store = LocalMaterialStore(
        app_settings.material_storage_path,
        catalog=material_catalog,
    )
    app.state.vector_store = LocalVectorStore(app_settings.material_storage_path)
    app.state.quiz_store = LocalQuizStore(app_settings.material_storage_path)
    app.state.quiz_job_store = SQLiteQuizJobStore(database)
    app.state.exam_store = LocalExamStore(app_settings.material_storage_path)
    app.state.package_service = PackageService(
        package_store=app.state.package_store,
        material_store=app.state.material_store,
        exam_store=app.state.exam_store,
        storage_root=app_settings.material_storage_path,
    )
    app.state.package_job_runner = PackageJobRunner(
        service=app.state.package_service,
        job_store=app.state.package_store,
    )
    app.state.question_quality_service = QuestionQualityInferenceService(
        checkpoint_path=app_settings.question_quality_checkpoint_path,
        enable_torch=app_settings.enable_torch_inference and app_settings.app_env != "test",
    )
    app.state.material_job_runner = MaterialJobRunner(
        IngestionPipeline(
            store=app.state.material_store,
            vector_store=app.state.vector_store,
        )
    )
    app.state.quiz_job_runner = QuizJobRunner(
        settings=app_settings,
        config_store=app.state.config_store,
        job_store=app.state.quiz_job_store,
        quiz_store=app.state.quiz_store,
        material_store=app.state.material_store,
        vector_store=app.state.vector_store,
        question_quality_service=app.state.question_quality_service,
        llm_client_registry=app.state.llm_client_registry,
        activity_store=app.state.activity_store,
    )

    local_origin_regex = (
        r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
        if app_settings.app_env != "production"
        else None
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[app_settings.frontend_origin],
        allow_origin_regex=local_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(activity.router, prefix="/api/v1")
    app.include_router(analytics.router, prefix="/api/v1")
    app.include_router(agents.router, prefix="/api/v1")
    app.include_router(config.router, prefix="/api/v1")
    app.include_router(courses.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(exams.router, prefix="/api/v1")
    app.include_router(materials.router, prefix="/api/v1")
    app.include_router(ml.router, prefix="/api/v1")
    app.include_router(notifications.router, prefix="/api/v1")
    app.include_router(packages.router, prefix="/api/v1")
    app.include_router(quiz.router, prefix="/api/v1")
    app.include_router(retrieval.router, prefix="/api/v1")
    app.include_router(source.router, prefix="/api/v1")
    app.include_router(workflow.router, prefix="/api/v1")
    app.state.package_job_runner.resume_incomplete_jobs()
    app.state.quiz_job_runner.resume_incomplete_jobs()
    return app


def _bootstrap_runtime_storage(settings: Settings) -> None:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    settings.material_storage_path.mkdir(parents=True, exist_ok=True)

    default_sqlite_path = DEFAULT_RUNTIME_ROOT / "exam_prep.sqlite3"
    default_material_storage_path = DEFAULT_RUNTIME_ROOT / "materials"
    legacy_root = PROJECT_ROOT / "data"
    legacy_sqlite_path = legacy_root / "exam_prep.sqlite3"
    legacy_material_storage_path = legacy_root / "materials"

    if settings.sqlite_path == default_sqlite_path and legacy_sqlite_path.exists() and not settings.sqlite_path.exists():
        shutil.copy2(legacy_sqlite_path, settings.sqlite_path)
        logger.info(
            "Migrated legacy sqlite storage from %s to %s",
            legacy_sqlite_path,
            settings.sqlite_path,
        )

    if (
        settings.material_storage_path == default_material_storage_path
        and legacy_material_storage_path.exists()
        and not any(settings.material_storage_path.iterdir())
    ):
        shutil.copytree(
            legacy_material_storage_path,
            settings.material_storage_path,
            dirs_exist_ok=True,
        )
        logger.info(
            "Migrated legacy material storage from %s to %s",
            legacy_material_storage_path,
            settings.material_storage_path,
        )


app = create_app()
