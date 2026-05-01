from pathlib import Path
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    openai_api_key: str
    spring_base_url: str = "http://localhost:8080"
    frontend_base_url: str = "http://localhost:5173"
    redis_url: str = "redis://localhost:6379"
    model_name: str = "gpt-4o-mini"
    request_timeout: float = 10.0

    class Config:
        env_file = _ENV_FILE


settings = Settings()
