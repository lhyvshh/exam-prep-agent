from typing import cast

from fastapi import Request

from exam_prep.core.config import Settings
from exam_prep.llm.base import LLMClient
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.repositories.activity_store import ActivityStore
from exam_prep.repositories.analytics_store import AnalyticsStore
from exam_prep.repositories.config_store import ConfigStore
from exam_prep.repositories.agent_store import AgentStore
from exam_prep.repositories.course_store import CourseStore
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_catalog import MaterialCatalog
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.notification_store import NotificationStore
from ..repositories.package_store import PackageStore
from exam_prep.repositories.quiz_job_store import QuizJobStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.repositories.workflow_store import WorkflowStore
from exam_prep.schemas.config import UserLLMConfig
from exam_prep.services.config_service import ConfigService
from exam_prep.services.material_job_runner import MaterialJobRunner
from exam_prep.services.quiz_job_runner import QuizJobRunner
from exam_prep.packages.jobs import PackageJobRunner
from exam_prep.packages.service import PackageService


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_config_store(request: Request) -> ConfigStore:
    return request.app.state.config_store  # type: ignore[no-any-return]


def get_agent_store(request: Request) -> AgentStore:
    return request.app.state.agent_store  # type: ignore[no-any-return]


def get_notification_store(request: Request) -> NotificationStore:
    return request.app.state.notification_store  # type: ignore[no-any-return]


def get_package_store(request: Request) -> PackageStore:
    return cast(PackageStore, request.app.state.package_store)


def get_package_service(request: Request) -> PackageService:
    return cast(PackageService, request.app.state.package_service)


def get_package_job_runner(request: Request) -> PackageJobRunner:
    return cast(PackageJobRunner, request.app.state.package_job_runner)


def get_activity_store(request: Request) -> ActivityStore:
    return request.app.state.activity_store  # type: ignore[no-any-return]


def get_analytics_store(request: Request) -> AnalyticsStore:
    return request.app.state.analytics_store  # type: ignore[no-any-return]


def get_material_store(request: Request) -> MaterialStore:
    return request.app.state.material_store  # type: ignore[no-any-return]


def get_course_store(request: Request) -> CourseStore:
    return request.app.state.course_store  # type: ignore[no-any-return]


def get_material_catalog(request: Request) -> MaterialCatalog:
    return request.app.state.material_catalog  # type: ignore[no-any-return]


def get_vector_store(request: Request) -> VectorStore:
    return request.app.state.vector_store  # type: ignore[no-any-return]


def get_quiz_store(request: Request) -> QuizStore:
    return request.app.state.quiz_store  # type: ignore[no-any-return]


def get_quiz_job_store(request: Request) -> QuizJobStore:
    return request.app.state.quiz_job_store  # type: ignore[no-any-return]


def get_exam_store(request: Request) -> ExamStore:
    return request.app.state.exam_store  # type: ignore[no-any-return]


def get_workflow_store(request: Request) -> WorkflowStore:
    return request.app.state.workflow_store  # type: ignore[no-any-return]


def get_question_quality_service(request: Request) -> QuestionQualityInferenceService:
    return request.app.state.question_quality_service  # type: ignore[no-any-return]


def get_runtime_llm_config(request: Request) -> UserLLMConfig:
    settings = get_app_settings(request)
    store = get_config_store(request)
    return ConfigService().get_runtime_config(settings, store).config


def get_parser_runtime_llm_config(request: Request) -> UserLLMConfig:
    settings = get_app_settings(request)
    store = get_config_store(request)
    return ConfigService().get_runtime_config(settings, store).parser_config


def get_llm_client_registry(request: Request) -> LLMClientRegistry:
    return request.app.state.llm_client_registry  # type: ignore[no-any-return]


def get_quiz_job_runner(request: Request) -> QuizJobRunner:
    return request.app.state.quiz_job_runner  # type: ignore[no-any-return]


def get_material_job_runner(request: Request) -> MaterialJobRunner:
    return request.app.state.material_job_runner  # type: ignore[no-any-return]


def get_runtime_llm_client(request: Request) -> LLMClient | None:
    config = get_runtime_llm_config(request)
    registry = get_llm_client_registry(request)
    return registry.get_or_create(config)
