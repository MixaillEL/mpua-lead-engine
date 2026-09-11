from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_NAME: str = "mpua_lead_engine"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""

    TEST_DB_HOST: str = "127.0.0.1"
    TEST_DB_PORT: int = 3306
    TEST_DB_NAME: str = "mpua_lead_engine_test"
    TEST_DB_USER: str = "root"
    TEST_DB_PASSWORD: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def test_database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.TEST_DB_USER}:{self.TEST_DB_PASSWORD}"
            f"@{self.TEST_DB_HOST}:{self.TEST_DB_PORT}/{self.TEST_DB_NAME}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
