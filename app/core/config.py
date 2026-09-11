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

    # Public Overpass endpoint = development / validation source only.
    # Do not point production high-volume traffic at it.
    OVERPASS_API_URL: str = "https://overpass-api.de/api/interpreter"
    OVERPASS_TIMEOUT: int = 60

    WEBSITE_TIMEOUT: int = 15
    WEBSITE_MAX_PAGES: int = 5
    WEBSITE_MAX_CONCURRENCY: int = 5
    WEBSITE_USER_AGENT: str = "MPUA-Lead-Engine/0.1"
    WEBSITE_MAX_RESPONSE_BYTES: int = 5_000_000

    TAVILY_API_KEY: str = ""
    TAVILY_API_URL: str = "https://api.tavily.com/search"
    TAVILY_SEARCH_DEPTH: str = "basic"
    TAVILY_MAX_RESULTS: int = 20
    TAVILY_TIMEOUT: int = 20
    TAVILY_MAX_REQUESTS_PER_JOB: int = 20
    TAVILY_COST_PER_CREDIT_USD: float = 0.008

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
