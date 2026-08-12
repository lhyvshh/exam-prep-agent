from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.repositories.config_store import ConfigStore
from exam_prep.schemas.config import LLMProvider, UserLLMConfig


class SQLiteConfigStore(ConfigStore):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get(self, profile: str = "current") -> UserLLMConfig | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT provider, model, api_key, demo_mode
                FROM llm_config
                WHERE config_id = ?
                """,
                (profile,),
            ).fetchone()

        if row is None:
            return None

        return UserLLMConfig(
            provider=LLMProvider(row["provider"]),
            model=row["model"],
            api_key=row["api_key"],
            demo_mode=bool(row["demo_mode"]),
        )

    def save(self, config: UserLLMConfig, profile: str = "current") -> UserLLMConfig:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO llm_config(config_id, provider, model, api_key, demo_mode)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(config_id) DO UPDATE SET
                    provider = excluded.provider,
                    model = excluded.model,
                    api_key = excluded.api_key,
                    demo_mode = excluded.demo_mode
                """,
                (
                    profile,
                    config.provider.value,
                    config.model,
                    config.api_key,
                    int(config.demo_mode),
                ),
            )
        return config
