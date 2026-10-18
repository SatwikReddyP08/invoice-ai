from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Invoice Processing System"
    API_V1_STR: str = "/api/v1"

    # Database configuration
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "invoice_app"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "invoice_db"
    POSTGRES_PORT: int = 5432

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.POSTGRES_PASSWORD:
            return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return f"postgresql://{self.POSTGRES_USER}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    # Storage
    STORAGE_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "storage")
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB

    # AI / External API
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"

    # Configurable Deterministic Analysis Thresholds
    PRICE_CHANGE_THRESHOLD_PERCENT: float = 10.0
    PRICE_CHANGE_MATERIAL_PERCENT: float = 25.0
    MONETARY_TOLERANCE: float = 0.05

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

settings = Settings()
