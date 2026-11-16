"""Deterministic Finite State Machine Orchestrator for Hardware Design Loop."""

from enum import Enum
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from eda.models import ToolReport, ToolStatus
from schemas.hardware import (
    CorrectionTask,
    MicroArchitecture,
    Requirements,
    ReviewFinding,
    RTLArtefact,
    VerificationPlan,
)
from schemas.run_layout import RunPaths, create_run_layout


class PipelineState(str, Enum):
    """The explicit operational states of the closed-loop design workflow."""
    IDLE = "IDLE"
    SPEC_ANALYSIS = "SPEC_ANALYSIS"
    ARCHITECTURE_DESIGN = "ARCHITECTURE_DESIGN"
    RTL_GENERATION = "RTL_GENERATION"
    VERIFICATION_GENERATION = "VERIFICATION_GENERATION"
    EDA_EXECUTION = "EDA_EXECUTION"
    REVIEW = "REVIEW"
    REFLECTION = "REFLECTION"
    CORRECTION = "CORRECTION"
    SUCCESS = "SUCCESS"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    FAILED = "FAILED"


class PipelineContext(BaseModel):
    """Encapsulates all mutable state, collateral, and artifacts for a pipeline run."""
    run_id: str
    run_paths: RunPaths
    spec_text: str
    current_state: PipelineState = PipelineState.IDLE
    iteration: int = 0
    max_iterations: int = 5
    requirements: Optional[Requirements] = None
    architecture: Optional[MicroArchitecture] = None
    rtl: Optional[RTLArtefact] = None
    verification: Optional[VerificationPlan] = None
    tool_reports: List[ToolReport] = Field(default_factory=list)
    review: Optional[ReviewFinding] = None
    correction: Optional[CorrectionTask] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


class Orchestrator:
    """Manages the iterative generate -> execute -> verify -> analyse -> correct loop."""

    def __init__(
        self,
        spec_agent: Optional[Any] = None,
        arch_agent: Optional[Any] = None,
        rtl_agent: Optional[Any] = None,
        verif_agent: Optional[Any] = None,
        eda_executor: Optional[Callable[[PipelineContext], List[ToolReport]]] = None,
        reviewer_agent: Optional[Any] = None,
        reflection_agent: Optional[Any] = None,
        enable_git_commits: bool = False,
    ):
        self.spec_agent = spec_agent
        self.arch_agent = arch_agent
        self.rtl_agent = rtl_agent
        self.verif_agent = verif_agent
        self.eda_executor = eda_executor
        self.reviewer_agent = reviewer_agent
        self.reflection_agent = reflection_agent
        self.enable_git_commits = enable_git_commits

    def _commit_state(self, ctx: PipelineContext, action_summary: str):
        """Optional Git commit for traceability across agent iterations."""
        if not self.enable_git_commits:
            return
        try:
            subprocess.run(["git", "add", "."], check=False, capture_output=True)
            msg = f"[{ctx.run_id}] Iteration {ctx.iteration}: {ctx.current_state.value} - {action_summary}"
            subprocess.run(["git", "commit", "-m", msg], check=False, capture_output=True)
        except Exception:
            pass

    def step(self, ctx: PipelineContext) -> PipelineState:
        """Executes a single state transition."""
        state = ctx.current_state

        if state == PipelineState.IDLE:
            # Save raw spec to run_dir/spec/spec.txt
            spec_file = ctx.run_paths.spec_dir / "spec.txt"
            with open(spec_file, "w", encoding="utf-8") as f:
                f.write(ctx.spec_text)
            ctx.current_state = PipelineState.SPEC_ANALYSIS
            return ctx.current_state

        elif state == PipelineState.SPEC_ANALYSIS:
            if not self.spec_agent:
                raise RuntimeError("Specification Agent not configured")
            ctx.requirements = self.spec_agent.execute(ctx.spec_text, run_id=ctx.run_id)
            # Persist requirements.json
            with open(ctx.run_paths.requirements_file, "w", encoding="utf-8") as f:
                f.write(ctx.requirements.model_dump_json(indent=2))
            ctx.current_state = PipelineState.ARCHITECTURE_DESIGN
            self._commit_state(ctx, "Extracted requirements")
            return ctx.current_state

        elif state == PipelineState.ARCHITECTURE_DESIGN:
            if not self.arch_agent:
                raise RuntimeError("Architect Agent not configured")
            ctx.architecture = self.arch_agent.execute(ctx.requirements, run_id=ctx.run_id)
            # Persist architecture.json
            with open(ctx.run_paths.architecture_file, "w", encoding="utf-8") as f:
                f.write(ctx.architecture.model_dump_json(indent=2))
            ctx.current_state = PipelineState.RTL_GENERATION
            self._commit_state(ctx, "Generated architecture plan")
            return ctx.current_state

        elif state == PipelineState.RTL_GENERATION:
            if not self.rtl_agent:
                raise RuntimeError("RTL Coder Agent not configured")
            context = {"requirements": ctx.requirements.model_dump()} if ctx.requirements else None
            ctx.rtl = self.rtl_agent.execute(ctx.architecture, run_id=ctx.run_id, context=context)
            # Persist RTL source
            rtl_path = ctx.run_paths.rtl_dir / f"{ctx.rtl.module_name}.v"
            with open(rtl_path, "w", encoding="utf-8") as f:
                f.write(ctx.rtl.rtl_code)
            ctx.rtl.file_path = rtl_path
            ctx.current_state = PipelineState.VERIFICATION_GENERATION
            self._commit_state(ctx, f"Generated RTL: {ctx.rtl.module_name}.v")
            return ctx.current_state

        elif state == PipelineState.VERIFICATION_GENERATION:
            if not self.verif_agent:
                raise RuntimeError("Verification Engineer Agent not configured")
            # Verification Engineer sees requirements, not the RTL code implementation!
            ctx.verification = self.verif_agent.execute(ctx.requirements, run_id=ctx.run_id)
            tb_path = ctx.run_paths.verification_dir / f"tb_{ctx.verification.top_module}.v"
            with open(tb_path, "w", encoding="utf-8") as f:
                f.write(ctx.verification.testbench_code)
            ctx.verification.file_path = tb_path
            ctx.current_state = PipelineState.EDA_EXECUTION
            self._commit_state(ctx, f"Generated Testbench: tb_{ctx.verification.top_module}.v")
            return ctx.current_state

        elif state == PipelineState.EDA_EXECUTION:
            if not self.eda_executor:
                raise RuntimeError("EDA Executor not configured")
            ctx.tool_reports = self.eda_executor(ctx)
            ctx.current_state = PipelineState.REVIEW
            return ctx.current_state

        elif state == PipelineState.REVIEW:
            if not self.reviewer_agent:
                raise RuntimeError("Reviewer Agent not configured")
            review_input = {
                "tool_reports": [r.model_dump() for r in ctx.tool_reports],
                "module_name": ctx.rtl.module_name if ctx.rtl else "unknown",
            }
            ctx.review = self.reviewer_agent.execute(review_input, run_id=ctx.run_id)

            # Persist review report
            review_file = ctx.run_paths.reports_dir / f"review_iter_{ctx.iteration}.json"
            with open(review_file, "w", encoding="utf-8") as f:
                f.write(ctx.review.model_dump_json(indent=2))

            if ctx.review.status == "PASS":
                ctx.current_state = PipelineState.SUCCESS
                self._commit_state(ctx, "Design verified and clean (PASS)")
            else:
                ctx.current_state = PipelineState.REFLECTION
            return ctx.current_state

        elif state == PipelineState.REFLECTION:
            if not self.reflection_agent:
                raise RuntimeError("Reflection Agent not configured")
            reflection_input = {
                "review": ctx.review.model_dump() if ctx.review else {},
                "iteration": ctx.iteration,
            }
            ctx.correction = self.reflection_agent.execute(reflection_input, run_id=ctx.run_id)

            # Check if human escalation was explicitly requested
            if ctx.correction.requires_human_escalation:
                ctx.current_state = PipelineState.HUMAN_ESCALATION
                return ctx.current_state

            ctx.current_state = PipelineState.CORRECTION
            return ctx.current_state

        elif state == PipelineState.CORRECTION:
            ctx.iteration += 1

            # Max iterations check
            if ctx.iteration >= ctx.max_iterations:
                ctx.current_state = PipelineState.HUMAN_ESCALATION
                return ctx.current_state

            # Route to target agent
            target = ctx.correction.target_agent if ctx.correction else "rtl_coder"
            if target == "rtl_coder":
                ctx.current_state = PipelineState.RTL_GENERATION
            elif target == "verification_engineer":
                ctx.current_state = PipelineState.VERIFICATION_GENERATION
            elif target == "architect":
                ctx.current_state = PipelineState.ARCHITECTURE_DESIGN
            else:
                ctx.current_state = PipelineState.RTL_GENERATION

            self._commit_state(ctx, f"Routed correction to {target} (Iter {ctx.iteration})")
            return ctx.current_state

        return ctx.current_state

    def run(self, ctx: PipelineContext) -> PipelineState:
        """Executes the state machine continuously until a terminal state is reached."""
        terminal_states = {
            PipelineState.SUCCESS,
            PipelineState.HUMAN_ESCALATION,
            PipelineState.FAILED,
        }

        while ctx.current_state not in terminal_states:
            self.step(ctx)

        return ctx.current_state
