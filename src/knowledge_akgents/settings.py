"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load ``.env`` into the process environment so the underlying clients (OpenAI,
# Tavily, Qdrant) — which read ``os.environ`` directly — see the credentials.
# ``pydantic-settings`` only populates this ``Settings`` object, not ``os.environ``,
# and ``uv run``/``uvicorn`` do not export ``.env`` on their own.
load_dotenv()


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

    # Local URL submission and ingestion-validator state. Delete this directory to
    # start over — it holds no data the knowledge graph itself needs.
    data_dir: str = "data"

    # HTTP server
    host: str = "*******"
    port: int = 8000

    @property
    def qdrant_enabled(self) -> bool:
        return bool(self.akgentic_qdrant_url.strip())

    @property
    def urls_file(self) -> Path:
        return Path(self.data_dir) / "urls.json"


settings = Settings()
