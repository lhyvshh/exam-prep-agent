from dataclasses import dataclass

from exam_prep.schemas.config import PublicAppConfig


@dataclass(slots=True)
class ConfigRepository:
    sqlite_path: str

    def get_config_snapshot(self) -> PublicAppConfig | None:
        return None
