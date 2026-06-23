"""Application configuration (pydantic-settings).

Local-first defaults: SQLite, in-memory queue, Ollama provider, Telegram/voice
disabled, network allowed but no cloud LLM keys required. Everything can be
overridden via environment variables or a `.env` file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = .../jarvis  (this file is backend/app/config.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    app_name: str = "JARVIS"
    environment: str = "local"
    debug: bool = True
    secret_key: str = Field(default="change-me-in-production")

    # --- API auth + CORS (a personal automation platform must not be open) ---
    # Auth is enforced when api_auth_enabled is true OR an api_token is set.
    api_auth_enabled: bool = False
    api_token: str | None = None
    cors_allow_origins_raw: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000", alias="CORS_ALLOW_ORIGINS"
    )

    # --- database / infra ---
    database_url: str = f"sqlite:///{(DATA_DIR / 'jarvis.db')}"
    redis_url: str = "redis://localhost:6379/0"

    # --- workspace & allowlists (security) ---
    workspace_root: str = str(DATA_DIR / "workspace")
    notes_dir: str = str(DATA_DIR / "notes")
    screenshots_dir: str = str(DATA_DIR / "screenshots")
    audit_dir: str = str(DATA_DIR / "audit")
    # Comma-separated; parsed via properties below.
    allowed_paths_raw: str = Field(default="", alias="ALLOWED_PATHS")
    allowed_domains_raw: str = Field(default="example.com,localhost", alias="ALLOWED_DOMAINS")
    command_allowlist_raw: str = Field(
        default="ls,cat,echo,pwd,whoami,date,uptime,df,free", alias="COMMAND_ALLOWLIST"
    )
    command_blocklist_raw: str = Field(
        default="rm -rf,mkfs,format,:(){,shutdown,reboot,dd if=,reg delete,netsh,iptables",
        alias="COMMAND_BLOCKLIST",
    )

    # --- policy toggles ---
    allow_low_risk_write: bool = True
    trusted_terminal_read: bool = False
    allow_network: bool = True
    default_mode: str = "SINGLE_BEST_MODEL"

    # --- LLM providers ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "llama3.1"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    groq_api_key: str | None = None
    openrouter_api_key: str | None = None
    openai_compatible_base_url: str | None = None
    # Fernet key for the encrypted credential vault (model API keys etc.).
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    vault_key: str | None = None

    # --- RAG / memory ---
    vector_backend: str = "memory"  # memory | local_vector | chroma | qdrant
    chroma_path: str = str(DATA_DIR / "memory" / "chroma")
    qdrant_url: str = "http://localhost:6333"
    # Embeddings for vector backends: hashing (offline default) | ollama |
    # sentence_transformers. ollama uses a local model (nomic-embed-text).
    embedding_provider: str = "hashing"
    embedding_model: str = "nomic-embed-text"

    # --- Telegram ---
    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_allowed_user_ids_raw: str = Field(default="", alias="TELEGRAM_ALLOWED_USER_IDS")

    # --- Voice (Phase 2) ---
    voice_enabled: bool = False
    stt_engine: str = "faster-whisper"
    stt_model: str = "base"
    tts_engine: str = "piper"
    piper_voice: str = "en_US-amy-medium"

    # --- Browser & web ---
    browser_headless: bool = False
    # Optional SearXNG/JSON search endpoint; if unset, web_search uses DuckDuckGo.
    search_api_url: str | None = None

    # --- Workflow scheduler (cron-driven background loop) ---
    scheduler_enabled: bool = False

    # --- safety: cap how many models a cascade/cost-saver run may try ---
    max_cascade_attempts: int = 4

    # --- safety: global session guardrails for autonomous/graph runs ---
    agent_max_actions: int = 25
    agent_max_seconds: float = 120.0
    session_max_cost: float = 10.0  # estimated cost units (paid model calls)

    # --- Phase 3 integrations (optional; outbound actions are approval-gated) ---
    github_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_access_token: str | None = None
    n8n_base_url: str | None = None

    # --- parsed list properties ---
    @property
    def allowed_paths(self) -> list[str]:
        base = [self.workspace_root, self.notes_dir, self.screenshots_dir]
        return base + _csv(self.allowed_paths_raw)

    @property
    def allowed_domains(self) -> list[str]:
        return _csv(self.allowed_domains_raw)

    @property
    def command_allowlist(self) -> list[str]:
        return _csv(self.command_allowlist_raw)

    @property
    def command_blocklist(self) -> list[str]:
        return _csv(self.command_blocklist_raw)

    @property
    def cors_allow_origins(self) -> list[str]:
        return _csv(self.cors_allow_origins_raw) or ["http://localhost:3000"]

    @property
    def auth_required(self) -> bool:
        return self.api_auth_enabled or bool(self.api_token)

    @property
    def telegram_allowed_user_ids(self) -> list[int]:
        out: list[int] = []
        for v in _csv(self.telegram_allowed_user_ids_raw):
            try:
                out.append(int(v))
            except ValueError:
                continue
        return out

    def ensure_dirs(self) -> None:
        for d in (
            DATA_DIR,
            Path(self.workspace_root),
            Path(self.notes_dir),
            Path(self.screenshots_dir),
            Path(self.audit_dir),
            Path(self.chroma_path),
        ):
            Path(d).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
