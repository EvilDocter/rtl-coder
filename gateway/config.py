"""Gateway Configuration and Environment Settings."""

import os
from pathlib import Path
from pydantic import BaseModel, Field


class GatewayConfig(BaseModel):
    """Runtime configuration for the local inference gateway."""

    # Ollama local endpoint
    ollama_base_url: str = Field(
        default=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        description="Local Ollama serving endpoint"
    )

    # Models
    primary_model: str = Field(
        default=os.getenv("GATEWAY_PRIMARY_MODEL", "qwen2.5-coder:7b-instruct-q4_K_M"),
        description="Primary workhorse model for complex reasoning and RTL design"
    )
    fast_model: str = Field(
        default=os.getenv("GATEWAY_FAST_MODEL", "qwen2.5-coder:1.5b"),
        description="Fast lightweight model for smoke tests and simple JSON transformations"
    )

    # Serving parameters
    host: str = Field(default="127.0.0.1", description="Gateway host bind address")
    port: int = Field(default=8000, description="Gateway port")
    request_timeout_seconds: float = Field(
        default=180.0,
        description="Timeout per LLM request in seconds (generous for CPU inference)"
    )
    max_retries: int = Field(default=3, description="Maximum retries for transient failures or invalid JSON")

    # Base workspace directory
    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent,
        description="Root path of the repository"
    )


# Global default configuration instance
config = GatewayConfig()
