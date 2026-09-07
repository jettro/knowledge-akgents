"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Knowledge Akgents backend.

    Credentials (``OPENAI_API_KEY``, optional ``OPENAI_BASE_URL``, ``TAVILY_API_KEY``)
    are read from the environment by the underlying clients directly; they are surfaced
    here only so the backend can warn when they are missing.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    llm_model: str = "gpt-5.6-luna"
    # llm_model: str = "gpt-4o-mini"
    llm_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    # Presence checks (values themselves are consumed by the provider clients via env)
    openai_api_key: str = ""
    openai_base_url: str = ""
    tavily_api_key: str = ""

    # Vector store (Qdrant). Exporting AKGENTIC_QDRANT_URL switches the backend to Qdrant.
    akgentic_qdrant_url: str = ""

    # HTTP server
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def qdrant_enabled(self) -> bool:
        return bool(self.akgentic_qdrant_url.strip())


settings = Settings()
