"""Safe Prompt configuration — Pydantic settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator


# Load environment from .env, searching up from cwd for robustness.
# pydantic's own env_file config loads into its settings namespace but does
# NOT populate os.environ, so we load dotenv here so the validators below can
# read QORECHAIN_ANCHOR_CONTRACT_ADDRESS via os.getenv.
def _load_env_file() -> Path | None:
    cur = Path.cwd()
    while True:
        candidate = cur / ".env"
        if candidate.exists():
            load_dotenv(candidate, override=False)
            return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


_load_env_file()


class Settings(BaseModel):
    """Application settings loaded from environment variables."""

    # QoreChain Diana testnet
    qorechain_network: str = Field(default="qorechain-diana")
    qorechain_chain_id: str = Field(default="9800")
    qorechain_rpc_url: str = Field(default="https://evm-testnet.qore.host")
    qorechain_explorer_url: str = Field(default="https://explore.qore.network")

    # SafePromptAnchor contract (Diana testnet) — read directly from
    # QORECHAIN_ANCHOR_CONTRACT_ADDRESS (no SAFE_PROMPT_ prefix)
    anchor_contract_address: Optional[str] = Field(default=None)

    # QoreChain PQC key registry
    kem_registry_address: Optional[str] = Field(default=None)
    ml_dsa_registry_address: Optional[str] = Field(default=None)

    # Local gateway
    gateway_host: str = Field(default="127.0.0.1")
    gateway_port: int = Field(default=8787)
    web_port: int = Field(default=8080)

    # Upstream LLM — any OpenAI-compatible Chat Completions endpoint
    # (OpenRouter, OmniRouter, OpenAI, Groq, Together, local vLLM/Ollama, ...)
    upstream_llm_url: Optional[str] = Field(default=None)
    upstream_api_key: Optional[str] = Field(default=None)
    upstream_referer: Optional[str] = Field(default=None)
    upstream_title: Optional[str] = Field(default=None)
    default_model: str = Field(default="qorechain-mock-model")
    local_model: Optional[str] = Field(default=None)

    # TUI session
    session_name: str = Field(default="tui")
    save_dir: Path = Field(default_factory=lambda: Path.home() / ".safe-prompt" / "transcripts")

    # Detection rules
    fail_closed: bool = Field(default=True)
    detection_rules_path: Optional[str] = Field(default=None)

    # Rust core fallback
    use_rust_core: bool = Field(default=True)

    class Config:
        env_file = ".env"
        env_prefix = "SAFE_PROMPT_"
        case_sensitive = False

    @model_validator(mode="before")
    @classmethod
    def _read_prefixed_env(cls, data: Any) -> Any:
        """Read SAFE_PROMPT_* environment variables.

        Settings is a plain BaseModel, so pydantic's Config.env_file/env_prefix
        are inert. Load the prefixed variables explicitly instead.
        """
        if isinstance(data, dict):
            for name in cls.model_fields:
                key = f"SAFE_PROMPT_{name.upper()}"
                if key in os.environ and name not in data:
                    data[name] = os.environ[key]
        return data

    @model_validator(mode="after")
    def _read_anchor_address(self) -> "Settings":
        """Fall back to QORECHAIN_ANCHOR_CONTRACT_ADDRESS (no prefix) when not set."""
        if not self.anchor_contract_address:
            self.anchor_contract_address = os.getenv("QORECHAIN_ANCHOR_CONTRACT_ADDRESS")
        return self


def load_settings() -> Settings:
    return Settings()