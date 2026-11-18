"""Phase 6 Tests: Autonomous Verification Engineer & Script Engineer Agents."""

from pathlib import Path
import pytest

from agents import (
    ArchitectAgent,
    ReflectionAgent,
    ReviewerAgent,
    RTLCoderAgent,
    ScriptEngineerAgent,
    SpecificationAnalystAgent,
    VerificationEngineerAgent,
)
from eda import IVerilogWrapper, YosysWrapper
from gateway.config import config
from gateway.gateway_client import InferenceGatewayClient
from orchestrator import Orchestrator, PipelineContext, PipelineState, RealEDAExecutor
from schemas import (
    ClockConfig,
    PortDirection,
    Requirements,
    ResetConfig,
    ResetType,
    SignalPort,
    create_run_layout,
)


@pytest.fixture
def counter_reqs() -> Requirements:
    return Requirements(
        module_name="counter",
        summary="8-bit synchronous up-counter with active-low reset and overflow indicator",
        clocking=ClockConfig(clock_name="clk", edge="posedge", frequency_mhz=100.0),
        resets=[ResetConfig(signal_name="rst_n", active_level="low", type=ResetType.SYNCHRONOUS)],
        ports=[
            SignalPort(name="clk", direction=PortDirection.INPUT, width_bits=1, description="Clock"),
            SignalPort(name="rst_n", direction=PortDirection.INPUT, width_bits=1, description="Active-low reset"),
            SignalPort(name="enable", direction=PortDirection.INPUT, width_bits=1, description="Enable count"),
            SignalPort(name="count", direction=PortDirection.OUTPUT, width_bits=8, description="Current count"),
            SignalPort(name="overflow", direction=PortDirection.OUTPUT, width_bits=1, description="Overflow flag"),
        ],
        parameters=[],
        functional_requirements=[
            "When rst_n is low, count is 0 and overflow is 0",
            "When enable is high on posedge clk, count increments by 1",
            "When count == 255 and enable is high, overflow is 1",
        ],
        corner_cases=["Reset during counting", "Overflow wrap-around at 255"],
    )


def test_verification_engineer_generation(counter_reqs: Requirements, tmp_path: Path):
    """Verifies that the Verification Engineer autonomously writes a valid, compilable testbench."""
    client = InferenceGatewayClient()
    primary_model = config.primary_model

    verif_agent = VerificationEngineerAgent(gateway_client=client, model=primary_model, temperature=0.0)
    verif_plan = verif_agent.execute(counter_reqs, run_id="test_verif_gen")

    assert verif_plan.top_module == "counter"
    assert "tb_counter" in verif_plan.testbench_code
    assert "counter" in verif_plan.testbench_code
    assert "$finish" in verif_plan.testbench_code
    assert len(verif_plan.test_scenarios) > 0

    # Test that the generated testbench compiles cleanly with a golden counter RTL
    golden_counter_rtl = """module counter (
  input wire clk,
  input wire rst_n,
  input wire enable,
  output reg [7:0] count,
  output reg overflow
);
  always @(posedge clk) begin
    if (!rst_n) begin
      count <= 8'd0;
      overflow <= 1'b0;
    end else begin
      if (enable) begin
        count <= count + 1'b1;
        overflow <= (count == 8'd255);
      end else begin
        overflow <= 1'b0;
      end
    end
  end
endmodule
"""
    rtl_file = tmp_path / "counter.v"
    tb_file = tmp_path / "tb_counter.v"
    vvp_file = tmp_path / "counter.vvp"

    rtl_file.write_text(golden_counter_rtl, encoding="utf-8")
    tb_file.write_text(verif_plan.testbench_code, encoding="utf-8")

    iverilog = IVerilogWrapper()
    compile_report = iverilog.compile([rtl_file, tb_file], output_vvp=vvp_file)

    assert compile_report.status.value == "PASS", f"Testbench compile failed: {compile_report.stderr}"


def test_script_engineer_yosys_generation(tmp_path: Path):
    """Verifies that the Script Engineer generates valid, executable Yosys synthesis scripts."""
    client = InferenceGatewayClient()
    fast_model = config.fast_model

    script_agent = ScriptEngineerAgent(gateway_client=client, model=fast_model, temperature=0.0)
    task_input = {
        "tool": "yosys",
        "top_module": "counter",
        "sources": ["counter.v"],
        "output_file": "counter_syn.v",
    }
    script = script_agent.execute(task_input, run_id="test_script_yosys")

    assert script.tool == "yosys"
    assert script_agent.validate_script(script)
    assert "counter" in script.script_content
    assert "counter_syn.v" in script.expected_outputs or "counter_syn.v" in script.script_content


def test_script_engineer_makefile_generation():
    """Verifies that the Script Engineer generates clean Makefiles for simulation."""
    client = InferenceGatewayClient()
    fast_model = config.fast_model

    script_agent = ScriptEngineerAgent(gateway_client=client, model=fast_model, temperature=0.0)
    task_input = {
        "tool": "iverilog",
        "top_module": "counter",
        "sources": ["rtl/counter.v", "verification/tb_counter.v"],
    }
    script = script_agent.execute(task_input, run_id="test_script_make")

    assert script.tool == "iverilog"
    assert script.script_type == "makefile"
    assert "iverilog" in script.script_content
    assert "vvp" in script.script_content


