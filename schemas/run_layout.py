"""Deterministic Per-Run Artefact Layout and Workspace Management.

Synopsis Requirement:
"A shared, version-controlled repository maintains specifications,
architecture descriptions, RTL, verification files, scripts, reports,
and revision history generated throughout the workflow."
"""

from __future__ import annotations

import datetime
from pathlib import Path
from pydantic import BaseModel, Field


class RunPaths(BaseModel):
    """Strongly-typed absolute paths for an isolated pipeline execution run."""

    run_id: str
    run_dir: Path
    spec_dir: Path
    requirements_file: Path
    architecture_file: Path
    rtl_dir: Path
    verification_dir: Path
    scripts_dir: Path
    reports_dir: Path
    history_dir: Path

    model_config = {"arbitrary_types_allowed": True}

    def to_wsl_path(self, path: Path) -> str:
        """Converts a Windows path (e.g. C:\\Users\\...) to a WSL path (/mnt/c/Users/...)."""
        resolved = str(path.resolve()).replace("\\", "/")
        if len(resolved) >= 2 and resolved[1] == ":":
            drive = resolved[0].lower()
            return f"/mnt/{drive}{resolved[2:]}"
        return resolved


def create_run_layout(
    run_id: str | None = None,
    base_dir: Path | None = None,
) -> RunPaths:
    """Creates and returns the standardized directory layout for a pipeline run.

    Layout:
    runs/<run_id>/
      ├── spec/
      ├── requirements.json
      ├── architecture.json
      ├── rtl/
      ├── verification/
      ├── scripts/
      ├── reports/
      └── history/
    """
    if run_id is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{timestamp}"

    if base_dir is None:
        # Default to repo root / runs
        base_dir = Path(__file__).resolve().parent.parent / "runs"

    run_dir = Path(base_dir) / run_id
    spec_dir = run_dir / "spec"
    rtl_dir = run_dir / "rtl"
    verification_dir = run_dir / "verification"
    scripts_dir = run_dir / "scripts"
    reports_dir = run_dir / "reports"
    history_dir = run_dir / "history"

    # Create directories if they do not exist
    for directory in [spec_dir, rtl_dir, verification_dir, scripts_dir, reports_dir, history_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    return RunPaths(
        run_id=run_id,
        run_dir=run_dir,
        spec_dir=spec_dir,
        requirements_file=run_dir / "requirements.json",
        architecture_file=run_dir / "architecture.json",
        rtl_dir=rtl_dir,
        verification_dir=verification_dir,
        scripts_dir=scripts_dir,
        reports_dir=reports_dir,
        history_dir=history_dir,
    )
