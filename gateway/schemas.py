"""Request and response schemas for the local inference gateway."""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """The 7 specialized agents defined in the project synopsis."""
    SPECIFICATION_ANALYST = "specification_analyst"
    ARCHITECT = "architect"
    RTL_CODER = "rtl_coder"
    VERIFICATION_ENGINEER = "verification_engineer"
    SCRIPT_ENGINEER = "script_engineer"
    REVIEWER = "reviewer"
    REFLECTION = "reflection"
    GENERIC = "generic"


class GenerateRequest(BaseModel):
    """Input payload for the /generate gateway endpoint."""
    prompt: str = Field(..., description="User/agent prompt instructions")
    agent_role: AgentRole = Field(
        default=AgentRole.GENERIC,
        description="Role of the calling agent (selects default system prompt)"
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Custom system prompt override; defaults to the curated agent prompt"
    )
    model: Optional[str] = Field(
        default=None,
        description="Model name override; defaults to config.primary_model"
    )
    json_mode: bool = Field(
        default=True,
        description="Force JSON-formatted output from the model"
    )
    expected_json_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional JSON schema to validate output structure against"
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Sampling temperature; low for deterministic engineering outputs"
    )
    run_id: Optional[str] = Field(
        default=None,
        description="Active run identifier for directory-level audit logging"
    )


class GenerateResponse(BaseModel):
    """Output payload from the /generate gateway endpoint."""
    success: bool = Field(..., description="Whether generation and validation succeeded")
    content: Union[Dict[str, Any], List[Any], str] = Field(
        ...,
        description="Parsed JSON payload (if json_mode=True) or raw text content"
    )
    raw_content: str = Field(..., description="Unmodified response string from the model")
    model_used: str = Field(..., description="Exact model tag that executed inference")
    latency_ms: float = Field(..., description="Inference turnaround time in milliseconds")
    tokens_evaluated: Optional[int] = Field(default=None, description="Prompt token count")
    tokens_generated: Optional[int] = Field(default=None, description="Completion token count")
    retries_used: int = Field(default=0, description="Number of retry attempts required")
    error_message: Optional[str] = Field(default=None, description="Error detail if generation failed")


class HealthResponse(BaseModel):
    """Gateway health check and model availability status."""
    status: str
    ollama_connected: bool
    primary_model: str
    available_models: List[str]
    host: str
    port: int
