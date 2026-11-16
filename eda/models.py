"""Standardized EDA Tool Reporting Schemas."""

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolStatus(str, Enum):
    """Standardized execution outcome across all EDA tools."""
    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class ToolMessageSeverity(str, Enum):
    """Severity classification for parsed log messages."""
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ToolMessage(BaseModel):
    """Structured compiler/linter message with source location."""
    severity: ToolMessageSeverity
    file: Optional[str] = None
    line: Optional[int] = None
    col: Optional[int] = None
    code: Optional[str] = None  # e.g., "WIDTH", "COMBDLY", "syntax error"
    message: str


class ToolReport(BaseModel):
    """Comprehensive, machine-readable report generated after an EDA tool run."""
    tool_name: str = Field(..., description="Tool name: iverilog, verilator, yosys, etc.")
    stage: str = Field(..., description="Stage: compile, sim, lint, synth, coverage")
    status: ToolStatus = Field(..., description="PASS or FAIL status")
    exit_code: int = Field(..., description="Process exit code")
    messages: List[ToolMessage] = Field(default_factory=list, description="Parsed diagnostic messages")
    error_count: int = 0
    warning_count: int = 0
    runtime_ms: float = 0.0
    raw_log_path: Optional[Path] = None
    stdout: str = ""
    stderr: str = ""
    waveform_path: Optional[Path] = None
    metrics: Dict[str, Any] = Field(default_factory=dict, description="e.g. cell_count, gates, dffs")

    model_config = {"arbitrary_types_allowed": True}
