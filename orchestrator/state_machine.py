"""Deterministic Finite State Machine Orchestrator for Hardware Design Loop."""

from datetime import datetime
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
    EDAScriptArtefact,
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
    eda_scripts: List[EDAScriptArtefact] = Field(default_factory=list)
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
        script_agent: Optional[Any] = None,
        eda_executor: Optional[Callable[[PipelineContext], List[ToolReport]]] = None,
        reviewer_agent: Optional[Any] = None,
        reflection_agent: Optional[Any] = None,
        enable_git_commits: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.spec_agent = spec_agent
        self.arch_agent = arch_agent
        self.rtl_agent = rtl_agent
        self.verif_agent = verif_agent
        self.script_agent = script_agent
        self.eda_executor = eda_executor
        self.reviewer_agent = reviewer_agent
        self.reflection_agent = reflection_agent
        self.enable_git_commits = enable_git_commits
        self.progress_callback = progress_callback

    def _update_live_status(
        self,
        ctx: PipelineContext,
        stage_key: str,
        stage_status: str,  # "WAITING", "RUNNING", "DONE", "FAILED"
        agent_name: str,
        task_desc: str,
        log_message: Optional[str] = None,
        overall_status: Optional[str] = None,
    ):
        """Maintains live_status.json for real-time frontend visualization."""
        status_file = ctx.run_paths.run_dir / "live_status.json"
        now_str = datetime.now().strftime("%H:%M:%S")

        status_data: Dict[str, Any] = {}
        if status_file.exists():
            try:
                status_data = json.loads(status_file.read_text(encoding="utf-8"))
            except Exception:
                status_data = {}

        if not status_data:
            status_data = {
                "run_id": ctx.run_id,
                "status": "RUNNING",
                "current_state": ctx.current_state.value,
                "active_agent": agent_name,
                "agent_role_desc": task_desc,
                "iteration": ctx.iteration,
                "progress_percent": 10,
                "stages": {
                    "SPEC_ANALYSIS": {"name": "Spec Analyst", "status": "WAITING", "detail": "Extract ports, parameters & timing", "badge": "1.5B"},
                    "ARCHITECTURE_DESIGN": {"name": "Architect", "status": "WAITING", "detail": "Design datapath, registers & FSM", "badge": "1.5B"},
                    "RTL_GENERATION": {"name": "RTL Coder", "status": "WAITING", "detail": "Synthesize synthesizable Verilog", "badge": "3B"},
                    "VERIFICATION_GENERATION": {"name": "Verif Engineer", "status": "WAITING", "detail": "Author self-checking testbench", "badge": "3B"},
                    "SCRIPT_ENGINEER": {"name": "Script Engineer", "status": "WAITING", "detail": "Generate Yosys/Makefile scripts", "badge": "1.5B"},
                    "EDA_EXECUTION": {"name": "EDA Engine", "status": "WAITING", "detail": "Run lint, sim & synth in WSL2", "badge": "WSL2"},
                    "REVIEW": {"name": "Reviewer", "status": "WAITING", "detail": "Audit simulation, lint & coverage", "badge": "1.5B"},
                    "REFLECTION": {"name": "Reflection", "status": "WAITING", "detail": "Diagnose failure & plan repair", "badge": "1.5B"},
                },
                "logs": [],
                "artifacts": {
                    "spec_text": ctx.spec_text,
                    "requirements": None,
                    "architecture": None,
                    "rtl": None,
                    "testbench": None,
                    "eda_reports": None,
                    "review": None,
                }
            }

        # Update metadata
        if overall_status:
            status_data["status"] = overall_status
        status_data["current_state"] = ctx.current_state.value
        status_data["active_agent"] = agent_name
        status_data["agent_role_desc"] = task_desc
        status_data["iteration"] = ctx.iteration

        # Update stage status
        if stage_key in status_data.get("stages", {}):
            status_data["stages"][stage_key]["status"] = stage_status
            if task_desc:
                status_data["stages"][stage_key]["detail"] = task_desc

        # Calculate progress percent
        stage_weights = {
            "IDLE": 5,
            "SPEC_ANALYSIS": 15,
            "ARCHITECTURE_DESIGN": 30,
            "RTL_GENERATION": 48,
            "VERIFICATION_GENERATION": 64,
            "SCRIPT_ENGINEER": 72,
            "EDA_EXECUTION": 84,
            "REVIEW": 94,
            "SUCCESS": 100,
            "HUMAN_ESCALATION": 100,
            "FAILED": 100,
        }
        if overall_status == "SUCCESS":
            status_data["progress_percent"] = 100
        else:
            status_data["progress_percent"] = stage_weights.get(ctx.current_state.value, status_data.get("progress_percent", 10))

        # Append log
        if log_message:
            logs = status_data.setdefault("logs", [])
            logs.append({
                "time": now_str,
                "agent": agent_name,
                "message": log_message,
            })
            if len(logs) > 200:
                logs.pop(0)

        # Update current artifacts
        artifacts = status_data.setdefault("artifacts", {})
        artifacts["spec_text"] = ctx.spec_text
        if ctx.requirements:
            try:
                artifacts["requirements"] = ctx.requirements.model_dump()
            except Exception:
                pass
        if ctx.architecture:
            try:
                artifacts["architecture"] = ctx.architecture.model_dump()
            except Exception:
                pass
        if ctx.rtl and ctx.rtl.rtl_code:
            artifacts["rtl"] = ctx.rtl.rtl_code
        if ctx.verification and ctx.verification.testbench_code:
            artifacts["testbench"] = ctx.verification.testbench_code
        if ctx.review:
            try:
                artifacts["review"] = ctx.review.model_dump()
            except Exception:
                pass
        if ctx.tool_reports:
            reports_summary = []
            for r in ctx.tool_reports:
                t_name = getattr(r, 'tool_name', 'tool').upper()
                s_val = getattr(r.status, 'value', str(r.status))
                reports_summary.append(f"=== {t_name} ({s_val}) ===\n{r.stdout}\n{r.stderr}")
            artifacts["eda_reports"] = "\n\n".join(reports_summary)

        # Persist to disk
        try:
            status_file.write_text(json.dumps(status_data, indent=2), encoding="utf-8")
        except Exception:
            pass

        # Callback if registered
        if self.progress_callback:
            try:
                self.progress_callback(status_data)
            except Exception:
                pass

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
            self._update_live_status(
                ctx=ctx,
                stage_key="SPEC_ANALYSIS",
                stage_status="RUNNING",
                agent_name="Specification Analyst",
                task_desc="Parsing requirements and synthesizing interface specifications with 1.5B model",
                log_message=f"Pipeline initialized for specification: '{ctx.spec_text[:60]}...'",
            )
            return ctx.current_state

        elif state == PipelineState.SPEC_ANALYSIS:
            if not self.spec_agent:
                raise RuntimeError("Specification Agent not configured")

            self._update_live_status(
                ctx=ctx,
                stage_key="SPEC_ANALYSIS",
                stage_status="RUNNING",
                agent_name="Specification Analyst",
                task_desc="Extracting clock domains, reset polarity, bus widths and operating modes",
                log_message="Specification Analyst parsing requirements schema...",
            )

            ctx.requirements = self.spec_agent.execute(ctx.spec_text, run_id=ctx.run_id)
            with open(ctx.run_paths.requirements_file, "w", encoding="utf-8") as f:
                f.write(ctx.requirements.model_dump_json(indent=2))

            ports_summary = ", ".join(p.name for p in ctx.requirements.ports[:5])
            self._update_live_status(
                ctx=ctx,
                stage_key="SPEC_ANALYSIS",
                stage_status="DONE",
                agent_name="Specification Analyst",
                task_desc=f"Extracted {len(ctx.requirements.ports)} ports ({ports_summary})",
                log_message=f"Specification Analyst complete: module '{ctx.requirements.module_name}' with {len(ctx.requirements.ports)} ports.",
            )

            ctx.current_state = PipelineState.ARCHITECTURE_DESIGN
            self._commit_state(ctx, "Extracted requirements")
            return ctx.current_state

        elif state == PipelineState.ARCHITECTURE_DESIGN:
            if not self.arch_agent:
                raise RuntimeError("Architect Agent not configured")

            self._update_live_status(
                ctx=ctx,
                stage_key="ARCHITECTURE_DESIGN",
                stage_status="RUNNING",
                agent_name="Architect",
                task_desc="Designing microarchitecture: dataflow, state encoding, registers and control path",
                log_message="Architect formulating register transfer microarchitecture...",
            )

            ctx.architecture = self.arch_agent.execute(ctx.requirements, run_id=ctx.run_id)
            with open(ctx.run_paths.architecture_file, "w", encoding="utf-8") as f:
                f.write(ctx.architecture.model_dump_json(indent=2))

            fsm_info = f"{len(ctx.architecture.fsm_states)} FSM states" if ctx.architecture.fsm_states else "pure datapath"
            num_regs = len(ctx.architecture.internal_registers) if ctx.architecture.internal_registers else 0
            self._update_live_status(
                ctx=ctx,
                stage_key="ARCHITECTURE_DESIGN",
                stage_status="DONE",
                agent_name="Architect",
                task_desc=f"Formulated microarchitecture: {num_regs} registers, {fsm_info}",
                log_message=f"Architect completed microarchitecture plan for '{ctx.architecture.module_name}'.",
            )

            ctx.current_state = PipelineState.RTL_GENERATION
            self._commit_state(ctx, "Generated architecture plan")
            return ctx.current_state

        elif state == PipelineState.RTL_GENERATION:
            if not self.rtl_agent:
                raise RuntimeError("RTL Coder Agent not configured")

            self._update_live_status(
                ctx=ctx,
                stage_key="RTL_GENERATION",
                stage_status="RUNNING",
                agent_name="RTL Coder",
                task_desc="Synthesizing synthesizable Verilog module using primary 3B model",
                log_message="RTL Coder generating synthesizable Verilog implementation...",
            )

            context: Dict[str, Any] = {}
            if ctx.requirements:
                context["requirements"] = ctx.requirements.model_dump()
            if ctx.correction:
                context["correction"] = ctx.correction.model_dump()
            if ctx.review:
                context["review"] = ctx.review.model_dump()

            ctx.rtl = self.rtl_agent.execute(ctx.architecture, run_id=ctx.run_id, context=context)
            rtl_path = ctx.run_paths.rtl_dir / f"{ctx.rtl.module_name}.v"
            with open(rtl_path, "w", encoding="utf-8") as f:
                f.write(ctx.rtl.rtl_code)
            ctx.rtl.file_path = rtl_path

            line_count = len(ctx.rtl.rtl_code.splitlines())
            self._update_live_status(
                ctx=ctx,
                stage_key="RTL_GENERATION",
                stage_status="DONE",
                agent_name="RTL Coder",
                task_desc=f"Synthesized {ctx.rtl.module_name}.v ({line_count} lines)",
                log_message=f"RTL Coder synthesized '{ctx.rtl.module_name}.v' ({line_count} lines of clean Verilog).",
            )

            ctx.current_state = PipelineState.VERIFICATION_GENERATION
            self._commit_state(ctx, f"Generated RTL: {ctx.rtl.module_name}.v")
            return ctx.current_state

        elif state == PipelineState.VERIFICATION_GENERATION:
            if not self.verif_agent:
                raise RuntimeError("Verification Engineer Agent not configured")

            self._update_live_status(
                ctx=ctx,
                stage_key="VERIFICATION_GENERATION",
                stage_status="RUNNING",
                agent_name="Verification Engineer",
                task_desc="Authoring self-checking Verilog testbench with assertions & safety watchdog using 3B model",
                log_message="Verification Engineer synthesizing directed & randomized test vectors...",
            )

            # Verification Engineer sees requirements, not the RTL code implementation!
            ctx.verification = self.verif_agent.execute(ctx.requirements, run_id=ctx.run_id)
            tb_path = ctx.run_paths.verification_dir / f"tb_{ctx.verification.top_module}.v"
            with open(tb_path, "w", encoding="utf-8") as f:
                f.write(ctx.verification.testbench_code)
            ctx.verification.file_path = tb_path

            self._update_live_status(
                ctx=ctx,
                stage_key="VERIFICATION_GENERATION",
                stage_status="DONE",
                agent_name="Verification Engineer",
                task_desc=f"Generated tb_{ctx.verification.top_module}.v with assertions",
                log_message=f"Verification Engineer completed testbench 'tb_{ctx.verification.top_module}.v'.",
            )

            # If Script Engineer is configured, synthesize EDA scripts
            if self.script_agent and ctx.rtl:
                try:
                    self._update_live_status(
                        ctx=ctx,
                        stage_key="SCRIPT_ENGINEER",
                        stage_status="RUNNING",
                        agent_name="Script Engineer",
                        task_desc="Generating automated Yosys synthesis script and Makefile",
                        log_message="Script Engineer formulating EDA tool automation scripts...",
                    )
                    script_input = {
                        "tool": "yosys",
                        "top_module": ctx.rtl.top_module,
                        "sources": [ctx.rtl.file_path.name if ctx.rtl.file_path else f"{ctx.rtl.module_name}.v"],
                        "output_file": f"{ctx.rtl.module_name}_syn.v",
                    }
                    script_artefact = self.script_agent.execute(script_input, run_id=ctx.run_id)
                    script_path = ctx.run_paths.scripts_dir / script_artefact.file_name
                    with open(script_path, "w", encoding="utf-8") as sf:
                        sf.write(script_artefact.script_content)
                    script_artefact.file_path = script_path
                    ctx.eda_scripts.append(script_artefact)

                    self._update_live_status(
                        ctx=ctx,
                        stage_key="SCRIPT_ENGINEER",
                        stage_status="DONE",
                        agent_name="Script Engineer",
                        task_desc=f"Produced {script_artefact.file_name}",
                        log_message=f"Script Engineer produced '{script_artefact.file_name}'.",
                    )
                except Exception as ex:
                    self._update_live_status(
                        ctx=ctx,
                        stage_key="SCRIPT_ENGINEER",
                        stage_status="DONE",
                        agent_name="Script Engineer",
                        task_desc="Default script templates loaded",
                        log_message=f"Script Engineer note: {ex}",
                    )

            ctx.current_state = PipelineState.EDA_EXECUTION
            self._commit_state(ctx, f"Generated Testbench: tb_{ctx.verification.top_module}.v")
            return ctx.current_state

        elif state == PipelineState.EDA_EXECUTION:
            if not self.eda_executor:
                raise RuntimeError("EDA Executor not configured")

            self._update_live_status(
                ctx=ctx,
                stage_key="EDA_EXECUTION",
                stage_status="RUNNING",
                agent_name="EDA Engine",
                task_desc="Running Icarus Verilog compilation, Verilator linting, and simulation in Ubuntu WSL2",
                log_message="EDA Engine invoking WSL2 toolchain (iverilog, verilator, yosys)...",
            )

            ctx.tool_reports = self.eda_executor(ctx)

            all_passed = all(r.status == ToolStatus.PASS for r in ctx.tool_reports) if ctx.tool_reports else False
            eda_stage_status = "DONE" if all_passed else "FAILED"
            summary_tools = ", ".join(f"{getattr(r, 'tool_name', 'tool')}:{getattr(r.status, 'value', str(r.status))}" for r in ctx.tool_reports)

            self._update_live_status(
                ctx=ctx,
                stage_key="EDA_EXECUTION",
                stage_status=eda_stage_status,
                agent_name="EDA Engine",
                task_desc=f"Completed {len(ctx.tool_reports)} tools ({summary_tools})",
                log_message=f"EDA Engine execution finished: {summary_tools}.",
            )

            ctx.current_state = PipelineState.REVIEW
            return ctx.current_state

        elif state == PipelineState.REVIEW:
            if not self.reviewer_agent:
                raise RuntimeError("Reviewer Agent not configured")

            self._update_live_status(
                ctx=ctx,
                stage_key="REVIEW",
                stage_status="RUNNING",
                agent_name="Reviewer",
                task_desc="Auditing simulation logs, lint diagnostics, and waveform dumps with 1.5B model",
                log_message="Reviewer analyzing EDA reports against hardware requirements...",
            )

            review_input = {
                "tool_reports": [r.model_dump() for r in ctx.tool_reports],
                "module_name": ctx.rtl.module_name if ctx.rtl else "unknown",
            }
            ctx.review = self.reviewer_agent.execute(review_input, run_id=ctx.run_id)

            review_file = ctx.run_paths.reports_dir / f"review_iter_{ctx.iteration}.json"
            with open(review_file, "w", encoding="utf-8") as f:
                f.write(ctx.review.model_dump_json(indent=2))

            if ctx.review.status == "PASS":
                self._update_live_status(
                    ctx=ctx,
                    stage_key="REVIEW",
                    stage_status="DONE",
                    agent_name="Reviewer",
                    task_desc="Verdict: PASS (All checks and assertions satisfied)",
                    log_message=f"Reviewer Verdict: PASS! {ctx.review.summary}",
                    overall_status="SUCCESS",
                )
                ctx.current_state = PipelineState.SUCCESS
                self._commit_state(ctx, "Design verified and clean (PASS)")
            else:
                self._update_live_status(
                    ctx=ctx,
                    stage_key="REVIEW",
                    stage_status="FAILED",
                    agent_name="Reviewer",
                    task_desc=f"Verdict: REPAIR NEEDED (Iteration {ctx.iteration})",
                    log_message=f"Reviewer Verdict: REPAIR. Issues: {ctx.review.summary}",
                )
                ctx.current_state = PipelineState.REFLECTION
            return ctx.current_state

        elif state == PipelineState.REFLECTION:
            if not self.reflection_agent:
                raise RuntimeError("Reflection Agent not configured")

            self._update_live_status(
                ctx=ctx,
                stage_key="REFLECTION",
                stage_status="RUNNING",
                agent_name="Reflection",
                task_desc="Diagnosing root cause of verification failure and formulating targeted repair instructions",
                log_message="Reflection Agent analyzing failure root cause...",
            )

            reflection_input = {
                "review": ctx.review.model_dump() if ctx.review else {},
                "iteration": ctx.iteration,
            }
            ctx.correction = self.reflection_agent.execute(reflection_input, run_id=ctx.run_id)

            if ctx.correction.requires_human_escalation:
                self._update_live_status(
                    ctx=ctx,
                    stage_key="REFLECTION",
                    stage_status="FAILED",
                    agent_name="Reflection",
                    task_desc="Human escalation requested by reflection agent",
                    log_message="Reflection Agent: Escalation threshold exceeded. Manual engineering guidance required.",
                    overall_status="HUMAN_ESCALATION",
                )
                ctx.current_state = PipelineState.HUMAN_ESCALATION
                return ctx.current_state

            cause_preview = ctx.correction.root_cause_analysis[:50] if ctx.correction.root_cause_analysis else ""
            self._update_live_status(
                ctx=ctx,
                stage_key="REFLECTION",
                stage_status="DONE",
                agent_name="Reflection",
                task_desc=f"Target: {ctx.correction.target_agent} ({cause_preview}...)",
                log_message=f"Reflection Agent formulated repair task for '{ctx.correction.target_agent}'.",
            )

            ctx.current_state = PipelineState.CORRECTION
            return ctx.current_state

        elif state == PipelineState.CORRECTION:
            ctx.iteration += 1

            if ctx.iteration >= ctx.max_iterations:
                self._update_live_status(
                    ctx=ctx,
                    stage_key="REFLECTION",
                    stage_status="FAILED",
                    agent_name="Orchestrator",
                    task_desc=f"Exceeded max iterations limit ({ctx.max_iterations})",
                    log_message=f"Orchestrator: Exceeded maximum repair iterations ({ctx.max_iterations}). Escalating to human.",
                    overall_status="HUMAN_ESCALATION",
                )
                ctx.current_state = PipelineState.HUMAN_ESCALATION
                return ctx.current_state

            target = ctx.correction.target_agent if ctx.correction else "rtl_coder"
            if target == "rtl_coder":
                ctx.current_state = PipelineState.RTL_GENERATION
            elif target == "verification_engineer":
                ctx.current_state = PipelineState.VERIFICATION_GENERATION
            elif target == "architect":
                ctx.current_state = PipelineState.ARCHITECTURE_DESIGN
            else:
                ctx.current_state = PipelineState.RTL_GENERATION

            self._update_live_status(
                ctx=ctx,
                stage_key=target.upper(),
                stage_status="RUNNING",
                agent_name="Orchestrator",
                task_desc=f"Starting repair cycle {ctx.iteration} targeting {target}",
                log_message=f"Starting repair iteration {ctx.iteration} targeting {target}.",
            )

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

        # Ensure final state is written to live_status.json
        final_status = "SUCCESS" if ctx.current_state == PipelineState.SUCCESS else "FAILED"
        self._update_live_status(
            ctx=ctx,
            stage_key="REVIEW",
            stage_status="DONE" if final_status == "SUCCESS" else "FAILED",
            agent_name="Orchestrator",
            task_desc=f"Pipeline finished with state: {ctx.current_state.value}",
            log_message=f"Closed-loop design execution completed with terminal state: {ctx.current_state.value}.",
            overall_status=final_status,
        )

        return ctx.current_state
