from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    MCP_HOST: str = Field(default="0.0.0.0")
    MCP_PORT: int = Field(default=8085)  # Changed from 8080 to avoid conflict with Llama Model
    PYTHON_LOG_LEVEL: str = Field(default="INFO")


settings = Settings()


