"""Safe Prompt configuration — Pydantic settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Application settings loaded from environment variables."""

    # QoreChain Diana testnet
    qorechain_network: str = Field(default="qorechain-diana")
    qorechain_chain_id: str = Field(default="9800")
    qorechain_rpc_url: str = Field(default="https://diana-rpc.qorechain.io")
    qorechain_explorer_url: str = Field(default="https://explorer.diana.qorechain.io")

    # QoreChain PQC key registry
    kem_registry_address: Optional[str] = Field(default=None)
    ml_dsa_registry_address: Optional[str] = Field(default=None)

    # Local gateway
    gateway_host: str = Field(default="127.0.0.1")
    gateway_port: int = Field(default=8787)
    web_port: int = Field(default=8080)
    upstream_llm_url: Optional[str] = Field(default=None)
    upstream_api_key: Optional[str] = Field(default=None)
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


def load_settings() -> Settings:
    return Settings()
