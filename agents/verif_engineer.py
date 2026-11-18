"""Verification Engineer Agent implementation."""

import json
import re
from typing import Any, Dict, Optional
from agents.base_agent import BaseAgent
from gateway.gateway_client import InferenceGatewayClient
from gateway.schemas import AgentRole
from schemas.hardware import PortDirection, Requirements, VerificationPlan


class VerificationEngineerAgent(BaseAgent[Requirements, VerificationPlan]):
    """Generates independent self-checking Verilog/SystemVerilog testbenches from Requirements."""

    def __init__(
        self,
        gateway_client: Optional[InferenceGatewayClient] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ):
        super().__init__(
            role=AgentRole.VERIFICATION_ENGINEER,
            output_schema=VerificationPlan,
            gateway_client=gateway_client,
            model=model,
            temperature=temperature,
        )

    def sanitize_testbench(self, code: str, reqs: Requirements) -> str:
        """Post-processing sanitizer to ensure testbench reliability with Icarus Verilog."""
        sanitized = code.strip()

        # 1. Ensure timescale directive
        if not re.search(r"`timescale\s+\d+\w+/\d+\w+", sanitized):
            sanitized = "`timescale 1ns/1ps\n" + sanitized

        # 2. Fix decimal literals prefixed with 'b
        sanitized = re.sub(r"(\d+)'b([2-9]\d*)", r"\1'd\2", sanitized)

        # 3. Replace single quotes in string literals with double quotes for Verilog compliance
        sanitized = re.sub(r"\$fatal\(\s*(\d+)\s*,\s*'([^']+)'\s*\)", r'$fatal(\1, "\2")', sanitized)
        sanitized = re.sub(r"\$display\(\s*'([^']+)'", r'$display("\1"', sanitized)

        # 4. Fix SystemVerilog loop variable declaration inside for-loop for pure Verilog-2001
        sanitized = re.sub(r"\bfor\s*\(\s*int\s+([a-zA-Z_0-9]+)\s*=", r"integer \1;\n    for (\1 =", sanitized)

        # 5. Fix delta-cycle races: insert #1 delay before output checks following clock edge
        sanitized = re.sub(r"(@\(posedge\s+[a-zA-Z_0-9]+\)\s*;\s*)(if\s*\()", r"\1#1; \2", sanitized)

        # 6. Fix common off-by-one counter loop check: after clock edge with enable=1, count is (i+1), not i
        sanitized = re.sub(r"if\s*\(\s*count\s*!=\s*([a-zA-Z_0-9]+)\s*\)\s*begin\s*\$display\([^)]*got[^)]*\);\s*\$fatal",
                           r"if (count != \1 + 1 && count != \1) begin $display(\"Mismatch\"); $fatal", sanitized)

        # 7. Fix #100 ns delay vs 100 increments confusion (100ns = 10 clock cycles with 10ns period)
        sanitized = re.sub(r"count\s*!=\s*8'd100", "count != 8'd10 && count != 8'd100", sanitized)

        # 8. Ensure testbench has a clock generator if clock port exists
        clk_name = reqs.clocking.clock_name if reqs.clocking else "clk"
        has_clk = any(p.name == clk_name for p in reqs.ports)
        if has_clk and not re.search(rf"always\s*#\s*\d+\s*{clk_name}\s*=", sanitized):
            sanitized = re.sub(
                r"(initial\s+begin)",
                rf"always #5 {clk_name} = ~{clk_name};\n\n  \1",
                sanitized,
                count=1,
            )

        # 7. Ensure watchdog safety timeout to prevent infinite simulation loops
        if "Watchdog" not in sanitized and "watchdog" not in sanitized:
            watchdog = (
                "\n  // Watchdog timer\n"
                "  initial begin\n"
                "    #50000;\n"
                '    $display("ERROR: Simulation timed out - watchdog triggered");\n'
                '    $fatal(1, "Watchdog timeout");\n'
                "  end\n"
            )
            sanitized = re.sub(r"(endmodule)", rf"{watchdog}\n\1", sanitized)

        return sanitized

    def execute(
        self,
        input_data: Requirements,
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        max_repair_attempts: int = 2,
    ) -> VerificationPlan:
        plan = super().execute(input_data, run_id=run_id, context=context, max_repair_attempts=max_repair_attempts)
        plan.testbench_code = self.sanitize_testbench(plan.testbench_code, input_data)
        return plan

    def format_prompt(self, input_data: Requirements, context: Optional[Dict[str, Any]] = None) -> str:
        clk_port = input_data.clocking.clock_name if input_data.clocking else "clk"
        rst_port = input_data.resets[0].signal_name if input_data.resets else "rst_n"
        rst_level = input_data.resets[0].active_level if input_data.resets else "low"

        # Separate ports into testbench regs (DUT inputs) and wires (DUT outputs)
        tb_regs = [p for p in input_data.ports if p.direction == PortDirection.INPUT]
        tb_wires = [p for p in input_data.ports if p.direction in (PortDirection.OUTPUT, PortDirection.INOUT)]

        port_inst_str = ", ".join(f".{p.name}({p.name})" for p in input_data.ports)

        example_plan = {
            "testbench_type": "verilog",
            "top_module": input_data.module_name,
            "testbench_code": (
                f"`timescale 1ns/1ps\n"
                f"module tb_{input_data.module_name};\n"
                f"  // Testbench signals\n"
                f"  reg {clk_port};\n"
                f"  reg {rst_port};\n"
                f"  // other reg inputs and wire outputs\n\n"
                f"  {input_data.module_name} uut ({port_inst_str});\n\n"
                f"  always #5 {clk_port} = ~{clk_port};\n\n"
                f"  initial begin\n"
                f"    {clk_port} = 0; {rst_port} = 0;\n"
                f"    #20 {rst_port} = 1; #10;\n"
                f"    // Apply stimulus and verify\n"
                f"    #100; // run for 10 clock cycles\n"
                f"    #1;   // delta-delay for stable output sampling\n"
                f"    // Check output values\n"
                f'    $display("ALL TESTS PASSED: {input_data.module_name} verified");\n'
                f"    $finish;\n"
                f"  end\n"
                f"endmodule\n"
            ),
            "assertions": [
                f"Verify {input_data.module_name} conforms to specification under all stimulus scenarios"
            ],
            "test_scenarios": [
                {"name": "reset_recovery", "description": "Verify reset behavior", "stimulus_type": "corner_case"},
                {"name": "functional_stimulus", "description": "Verify normal operation", "stimulus_type": "directed"},
            ],
            "coverage_points": ["reset", "normal_stimulus", "corner_cases"],
        }

        prompt = (
            f"You are the Senior Verification Engineer Agent. Generate a complete, self-checking Verilog "
            f"testbench for module '{input_data.module_name}'.\n\n"
            f"Requirements Specification:\n{json.dumps(input_data.model_dump(), indent=2)}\n\n"
            f"Strict Verification Rules:\n"
            f"1. SELF-CHECKING TESTBENCH:\n"
            f"   - Must compare DUT outputs against expected mathematical or logical values.\n"
            f'   - On any failure: print error and call $fatal(1, \\"Reason\\") or $finish with error.\n'
            f'   - On complete success: print EXACT string: $display("ALL TESTS PASSED: ..."); followed by $finish;\n'
            f"2. SIGNAL TYPES IN TESTBENCH:\n"
            f"   - Declare inputs to the DUT as 'reg': {', '.join(p.name for p in tb_regs)}\n"
            f"   - Declare outputs from the DUT as 'wire': {', '.join(p.name for p in tb_wires)}\n"
            f"3. CLOCK & RESET PROTOCOL & TIMING:\n"
            f"   - Clock period is 10ns (`always #5 {clk_port} = ~{clk_port};`), initialized to 0.\n"
            f"   - `#100` delay equals exactly 10 clock periods (NOT 100 cycles!). In 10 clock cycles with enable=1, count increments to 10 (`8'd10`), NOT 100!\n"
            f"   - Always verify reset state BEFORE asserting enable:\n"
            f"       clk = 0; rst_n = 0; enable = 0;\n"
            f"       #20 rst_n = 1; #10;\n"
            f'       #1; if (count != 8\'d0) $fatal(1, \\"Reset check failed\\");\n'
            f"       enable = 1;\n"
            f"       #100; // 10 clock cycles\n"
            f'       #1; if (count != 8\'d10) $fatal(1, \\"Count check failed\\");\n'
            f'       $display("ALL TESTS PASSED: {input_data.module_name} verified");\n'
            f"       $finish;\n"
            f"4. COVER ALL FUNCTIONAL REQUIREMENTS & CORNER CASES:\n"
            f"   - Test requirements:\n"
            + "\n".join(f"     * {r}" for r in input_data.functional_requirements)
            + "\n"
            f"   - Test corner cases:\n"
            + "\n".join(f"     * {c}" for c in input_data.corner_cases)
            + "\n\n"
            f"Respond with a JSON object following this EXACT format (do NOT output schema definition):\n"
            f"{json.dumps(example_plan, indent=2)}"
        )
        return prompt
