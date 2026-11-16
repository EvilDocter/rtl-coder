"""Automated test suite for Phase 4: Agent Framework, Schemas & State Machine."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.base_agent import BaseAgent
from eda.models import ToolMessage, ToolMessageSeverity, ToolReport, ToolStatus
from gateway.schemas import AgentRole, GenerateResponse
from orchestrator.state_machine import Orchestrator, PipelineContext, PipelineState
from schemas import (
    CorrectionTask,
    FaultClassification,
    MicroArchitecture,
    PortDirection,
    Requirements,
    ReviewDefect,
    ReviewFinding,
    RTLArtefact,
    SignalPort,
    VerificationPlan,
    create_run_layout,
)


# -------------------------------------------------------------------------
# 1. Pydantic Hardware Schemas Tests
# -------------------------------------------------------------------------

def test_hardware_schemas_roundtrip():
    """Verify serialization and deserialization of all core hardware schemas."""
    # Requirements
    reqs = Requirements(
        module_name="alu_8bit",
        summary="8-bit Arithmetic Logic Unit",
        ports=[
            SignalPort(name="clk", direction=PortDirection.INPUT, width_bits=1),
            SignalPort(name="out", direction=PortDirection.OUTPUT, width_bits=8),
        ],
        functional_requirements=["Support ADD, SUB, AND, OR"],
        corner_cases=["Overflow on 8'hFF + 1"],
    )
    reqs_json = reqs.model_dump_json()
    assert Requirements.model_validate_json(reqs_json).module_name == "alu_8bit"

    # MicroArchitecture
    arch = MicroArchitecture(
        module_name="alu_8bit",
        architecture_overview="Combinational ALU with output register",
        control_logic=["Opcode decoder"],
    )
    assert MicroArchitecture.model_validate_json(arch.model_dump_json()).module_name == "alu_8bit"

    # RTLArtefact
    rtl = RTLArtefact(
        module_name="alu_8bit",
        top_module="alu_8bit",
        rtl_code="module alu_8bit; endmodule",
    )
    assert RTLArtefact.model_validate_json(rtl.model_dump_json()).top_module == "alu_8bit"

    # VerificationPlan
    verif = VerificationPlan(
        top_module="alu_8bit",
        testbench_code="module tb_alu; endmodule",
        assertions=["assert property (out <= 8'hFF);"],
    )
    assert len(VerificationPlan.model_validate_json(verif.model_dump_json()).assertions) == 1

    # ReviewFinding
    review = ReviewFinding(
        status="FAIL",
        summary="Found 1 syntax error",
        defects=[
            ReviewDefect(
                category="SYNTAX",
                severity="ERROR",
                message="Undefined identifier",
                line=22,
            )
        ],
    )
    assert ReviewFinding.model_validate_json(review.model_dump_json()).status == "FAIL"

    # CorrectionTask
    correction = CorrectionTask(
        root_cause_analysis="Missing wire declaration",
        target_agent="rtl_coder",
        fault_classification=FaultClassification.RTL_BUG,
        specific_corrections=["Declare wire bad_signal;"],
    )
    assert CorrectionTask.model_validate_json(correction.model_dump_json()).target_agent == "rtl_coder"


# -------------------------------------------------------------------------
# 2. BaseAgent Schema Validation & Self-Repair Tests
# -------------------------------------------------------------------------

def test_base_agent_validation_and_repair():
    """Verify that BaseAgent validates output and triggers repair prompts on invalid schema."""
    mock_gateway = MagicMock()

    # 1st call returns invalid data (missing required summary)
    bad_resp = GenerateResponse(
        success=True,
        content={"module_name": "counter"},  # missing 'summary'
        raw_content='{"module_name": "counter"}',
        model_used="fake_model",
        latency_ms=10.0,
    )
    # 2nd call returns valid data after repair prompt
    good_resp = GenerateResponse(
        success=True,
        content={"module_name": "counter", "summary": "8-bit counter"},
        raw_content='{"module_name": "counter", "summary": "8-bit counter"}',
        model_used="fake_model",
        latency_ms=12.0,
    )
    mock_gateway.generate.side_effect = [bad_resp, good_resp]

    agent = BaseAgent(
        role=AgentRole.SPECIFICATION_ANALYST,
        output_schema=Requirements,
        gateway_client=mock_gateway,
    )

    result = agent.execute("Design an 8-bit counter")
    assert isinstance(result, Requirements)
    assert result.module_name == "counter"
    assert result.summary == "8-bit counter"
    # Assert 2 calls occurred (1 initial + 1 self-repair retry)
    assert mock_gateway.generate.call_count == 2


# -------------------------------------------------------------------------
# 3. Deterministic Mock Agents & Orchestrator State Machine Tests
# -------------------------------------------------------------------------

class MockSpecAgent:
    def execute(self, spec_text: str, run_id=None):
        return Requirements(
            module_name="mock_counter",
            summary="Deterministic mock counter",
            ports=[
                SignalPort(name="clk", direction=PortDirection.INPUT, width_bits=1),
                SignalPort(name="count", direction=PortDirection.OUTPUT, width_bits=8),
            ],
        )


class MockArchAgent:
    def execute(self, reqs: Requirements, run_id=None):
        return MicroArchitecture(
            module_name=reqs.module_name,
            architecture_overview="8-bit counter architecture",
        )


class MockRTLAgent:
    def __init__(self, produce_error_first=False):
        self.produce_error_first = produce_error_first
        self.call_count = 0

    def execute(self, arch: MicroArchitecture, run_id=None, context=None):
        self.call_count += 1
        return RTLArtefact(
            module_name=arch.module_name,
            top_module=arch.module_name,
            rtl_code=f"// Version {self.call_count}\nmodule {arch.module_name}; endmodule",
        )


class MockVerifAgent:
    def execute(self, reqs: Requirements, run_id=None):
        return VerificationPlan(
            top_module=reqs.module_name,
            testbench_code=f"module tb_{reqs.module_name}; endmodule",
        )


def test_orchestrator_happy_path(tmp_path: Path):
    """End-to-End Phase 4 Test: pipeline passes cleanly through all states to SUCCESS."""
    run_paths = create_run_layout(run_id="run_mock_pass", base_dir=tmp_path)
    ctx = PipelineContext(
        run_id="run_mock_pass",
        run_paths=run_paths,
        spec_text="Specification: 8-bit counter with synchronous enable.",
    )

    # Clean EDA execution
    def mock_eda(context):
        return [
            ToolReport(tool_name="verilator", stage="lint", status=ToolStatus.PASS, exit_code=0),
            ToolReport(tool_name="vvp", stage="sim", status=ToolStatus.PASS, exit_code=0),
        ]

    mock_reviewer = MagicMock()
    mock_reviewer.execute.return_value = ReviewFinding(status="PASS", summary="Clean build and sim")

    orchestrator = Orchestrator(
        spec_agent=MockSpecAgent(),
        arch_agent=MockArchAgent(),
        rtl_agent=MockRTLAgent(),
        verif_agent=MockVerifAgent(),
        eda_executor=mock_eda,
        reviewer_agent=mock_reviewer,
        reflection_agent=MagicMock(),
    )

    final_state = orchestrator.run(ctx)

    assert final_state == PipelineState.SUCCESS
    assert ctx.requirements is not None
    assert ctx.architecture is not None
    assert ctx.rtl is not None
    assert ctx.verification is not None
    assert ctx.review is not None
    assert ctx.review.status == "PASS"

    # Verify per-run layout contains artifacts
    assert (run_paths.spec_dir / "spec.txt").exists()
    assert run_paths.requirements_file.exists()
    assert run_paths.architecture_file.exists()
    assert (run_paths.rtl_dir / "mock_counter.v").exists()
    assert (run_paths.verification_dir / "tb_mock_counter.v").exists()
    assert (run_paths.reports_dir / "review_iter_0.json").exists()


def test_orchestrator_repair_loop(tmp_path: Path):
    """Test closed-loop: Failure in Iteration 0 -> Reflection routes to RTL -> Success in Iteration 1."""
    run_paths = create_run_layout(run_id="run_mock_repair", base_dir=tmp_path)
    ctx = PipelineContext(
        run_id="run_mock_repair",
        run_paths=run_paths,
        spec_text="Specification: Counter",
    )

    mock_reviewer = MagicMock()
    # Iteration 0 fails, Iteration 1 passes
    mock_reviewer.execute.side_effect = [
        ReviewFinding(status="FAIL", summary="Simulation mismatch"),
        ReviewFinding(status="PASS", summary="All tests passed"),
    ]

    mock_reflection = MagicMock()
    mock_reflection.execute.return_value = CorrectionTask(
        root_cause_analysis="Wrong count increment logic",
        target_agent="rtl_coder",
        fault_classification=FaultClassification.RTL_BUG,
        specific_corrections=["Change count <= count to count <= count + 1"],
    )

    rtl_agent = MockRTLAgent()

    orchestrator = Orchestrator(
        spec_agent=MockSpecAgent(),
        arch_agent=MockArchAgent(),
        rtl_agent=rtl_agent,
        verif_agent=MockVerifAgent(),
        eda_executor=lambda c: [ToolReport(tool_name="vvp", stage="sim", status=ToolStatus.PASS, exit_code=0)],
        reviewer_agent=mock_reviewer,
        reflection_agent=mock_reflection,
    )

    final_state = orchestrator.run(ctx)

    assert final_state == PipelineState.SUCCESS
    assert ctx.iteration == 1
    assert rtl_agent.call_count == 2  # RTL agent was invoked twice (initial + repair)


def test_orchestrator_human_escalation_on_max_iterations(tmp_path: Path):
    """Test max-iterations guard: perpetual failures cleanly trigger HUMAN_ESCALATION."""
    run_paths = create_run_layout(run_id="run_mock_escalate", base_dir=tmp_path)
    ctx = PipelineContext(
        run_id="run_mock_escalate",
        run_paths=run_paths,
        spec_text="Specification: Complex peripheral",
        max_iterations=2,
    )

    mock_reviewer = MagicMock()
    # Always fails
    mock_reviewer.execute.return_value = ReviewFinding(status="FAIL", summary="Perpetual failure")

    mock_reflection = MagicMock()
    mock_reflection.execute.return_value = CorrectionTask(
        root_cause_analysis="Unresolvable conflict",
        target_agent="rtl_coder",
        fault_classification=FaultClassification.RTL_BUG,
    )

    orchestrator = Orchestrator(
        spec_agent=MockSpecAgent(),
        arch_agent=MockArchAgent(),
        rtl_agent=MockRTLAgent(),
        verif_agent=MockVerifAgent(),
        eda_executor=lambda c: [],
        reviewer_agent=mock_reviewer,
        reflection_agent=mock_reflection,
    )

    final_state = orchestrator.run(ctx)

    assert final_state == PipelineState.HUMAN_ESCALATION
    assert ctx.iteration >= 2


def test_orchestrator_explicit_human_escalation(tmp_path: Path):
    """Test that Reflection can explicitly request human intervention."""
    run_paths = create_run_layout(run_id="run_mock_explicit_escalate", base_dir=tmp_path)
    ctx = PipelineContext(
        run_id="run_mock_explicit_escalate",
        run_paths=run_paths,
        spec_text="Specification: Ambiguous requirement",
    )

    mock_reviewer = MagicMock()
    mock_reviewer.execute.return_value = ReviewFinding(status="FAIL", summary="Spec ambiguity")

    mock_reflection = MagicMock()
    mock_reflection.execute.return_value = CorrectionTask(
        root_cause_analysis="Conflicting clock domains in datasheet",
        target_agent="architect",
        fault_classification=FaultClassification.SPEC_AMBIGUITY,
        requires_human_escalation=True,
        escalation_reason="Clock domain relationship is not specified",
    )

    orchestrator = Orchestrator(
        spec_agent=MockSpecAgent(),
        arch_agent=MockArchAgent(),
        rtl_agent=MockRTLAgent(),
        verif_agent=MockVerifAgent(),
        eda_executor=lambda c: [],
        reviewer_agent=mock_reviewer,
        reflection_agent=mock_reflection,
    )

    final_state = orchestrator.run(ctx)

    assert final_state == PipelineState.HUMAN_ESCALATION
    assert ctx.correction.requires_human_escalation is True
