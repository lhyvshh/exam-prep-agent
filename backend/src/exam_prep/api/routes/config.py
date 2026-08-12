from fastapi import APIRouter, Depends, HTTPException, Query, status

from exam_prep.api.deps import get_app_settings, get_config_store, get_llm_client_registry
from exam_prep.core.config import Settings
from exam_prep.core.exceptions import ConfigurationError, LLMProviderError
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.repositories.config_store import ConfigStore
from exam_prep.schemas.config import (
    ConfigHealthResponse,
    ConfigValidationRequest,
    ConfigValidationResponse,
    PublicAppConfig,
    RuntimeConfigResponse,
)
from exam_prep.services.config_service import ConfigService

router = APIRouter(tags=["config"])


@router.get("/config", response_model=PublicAppConfig)
def read_config(settings: Settings = Depends(get_app_settings)) -> PublicAppConfig:
    service = ConfigService()
    return service.get_public_config(settings)


@router.get("/config/runtime", response_model=RuntimeConfigResponse)
def read_runtime_config(
    settings: Settings = Depends(get_app_settings),
    store: ConfigStore = Depends(get_config_store),
) -> RuntimeConfigResponse:
    service = ConfigService()
    return service.get_runtime_config(settings, store)


@router.post("/config/validate", response_model=ConfigValidationResponse)
def validate_config(
    payload: ConfigValidationRequest,
    profile: str = Query(default="current", pattern="^(current|butler|parser)$"),
    settings: Settings = Depends(get_app_settings),
    store: ConfigStore = Depends(get_config_store),
    llm_client_registry: LLMClientRegistry = Depends(get_llm_client_registry),
) -> ConfigValidationResponse:
    service = ConfigService()
    try:
        return service.validate_and_store(
            payload,
            store,
            settings,
            llm_client_registry=llm_client_registry,
            profile=profile,
        )
    except ConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/config/health", response_model=ConfigHealthResponse)
def config_health(store: ConfigStore = Depends(get_config_store)) -> ConfigHealthResponse:
    service = ConfigService()
    return service.get_config_health(store)
