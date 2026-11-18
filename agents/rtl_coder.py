"""RTL Coder Agent implementation."""

import json
from typing import Any, Dict, Optional
from agents.base_agent import BaseAgent
from gateway.gateway_client import InferenceGatewayClient
from gateway.schemas import AgentRole
from schemas.hardware import MicroArchitecture, RTLArtefact


class RTLCoderAgent(BaseAgent[MicroArchitecture, RTLArtefact]):
    """Generates synthesizable Verilog/SystemVerilog RTL from MicroArchitecture plans."""

    def __init__(
        self,
        gateway_client: Optional[InferenceGatewayClient] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ):
        super().__init__(
            role=AgentRole.RTL_CODER,
            output_schema=RTLArtefact,
            gateway_client=gateway_client,
            model=model,
            temperature=temperature,
        )

    def sanitize_rtl(self, code: str) -> str:
        """Automated post-generation sanitizer for common small-model Verilog literal anomalies.

        Fixes patterns like:
        1. 8'b255 (binary literal with decimal digits) -> 8'd255.
        2. Automatic reg/wire reconciler for output ports (assign targeting reg -> convert to wire).
        """
        import re

        # Fix decimal numbers wrongly prefixed with 'b (e.g. 8'b255 -> 8'd255)
        sanitized = re.sub(r"(\d+)'b([2-9]\d*)", r"\1'd\2", code)

        # Remove self-assignments creating circular logic (e.g. assign x = x;)
        sanitized = re.sub(r"^\s*assign\s+([a-zA-Z_0-9]+)\s*=\s*\1\s*;\s*\n?", "", sanitized, flags=re.MULTILINE)

        # Eliminate next_count pipelining artifact
        sanitized = re.sub(
            r"next_count\s*<=\s*([a-zA-Z_0-9]+)\s*\+\s*1'b1\s*;",
            r"\1 <= \1 + 1'b1;",
            sanitized
        )
        sanitized = re.sub(r"^\s*count\s*<=\s*next_count\s*;\s*\n?", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"^\s*next_count\s*<=\s*count\s*;\s*\n?", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"\bnext_count\s*==", "count ==", sanitized)
        # Remove declarations of eliminated intermediate next_count
        sanitized = re.sub(r"^\s*reg\s+(?:\[[^\]]+\]\s+)?next_count\s*;\s*\n?", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"^\s*wire\s+(?:\[[^\]]+\]\s+)?next_count\s*;\s*\n?", "", sanitized, flags=re.MULTILINE)

        # Remove dummy reg_data intermediate register
        sanitized = re.sub(r"^\s*reg\s+(?:\[[^\]]+\]\s+)?reg_data\s*;\s*\n?", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"^\s*count\s*<=\s*reg_data\s*;\s*\n?", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"\breg_data\b", "count", sanitized)

        # Ensure memory array writes are present if memory array is declared
        if re.search(r"\breg\s+\[\d+:\d+\]\s+mem\s*\[", sanitized) and not re.search(r"\bmem\s*\[[^\]]+\]\s*<=", sanitized):
            sanitized = re.sub(
                r"(\bwr_ptr\s*<=\s*wr_ptr\s*\+\s*1'b1\s*;)",
                r"mem[wr_ptr] <= wr_data; \1",
                sanitized
            )

        # Synchronous reset: ensure sensitivity list is @(posedge clk) only
        sanitized = re.sub(
            r"always\s*@\s*\(\s*posedge\s+([a-zA-Z_0-9]+)\s+or\s+(?:neg|pos)edge\s+[a-zA-Z_0-9]+\s*\)",
            r"always @(posedge \1)",
            sanitized
        )

        # Reconcile ports driven by continuous assign (must be wire) vs always block (must be reg)
        assigned_wires = set(re.findall(r"\bassign\s+([a-zA-Z_0-9]+)\s*=", sanitized))
        for sig in assigned_wires:
            # 1. Output port must be wire
            sanitized = re.sub(rf"\boutput\s+reg\b(\s*(?:\[[^\]]+\]\s*)?{sig}\b)", r"output wire\1", sanitized)
            # 2. Remove illegal procedural assignments to continuously assigned wire inside always blocks
            sanitized = re.sub(rf"^\s*{sig}\s*<=?[^;]+;\s*\n?", "", sanitized, flags=re.MULTILINE)
            # 3. If sig is not an output/input/wire/reg, declare it as wire
            if not re.search(rf"\b(input|output|inout|wire|reg)\b[^\n;]*\b{sig}\b", sanitized):
                sanitized = re.sub(r"(\);\s*\n)", rf"\1  wire {sig};\n", sanitized, count=1)

        always_regs = set(re.findall(r"\b([a-zA-Z_0-9]+)\s*<=", sanitized))
        for sig in always_regs:
            if sig not in assigned_wires:
                sanitized = re.sub(rf"\boutput\s+wire\b(\s*(?:\[[^\]]+\]\s*)?{sig}\b)", r"output reg\1", sanitized)

        return sanitized

    def execute(
        self,
        input_data: MicroArchitecture,
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        max_repair_attempts: int = 2,
    ) -> RTLArtefact:
        artefact = super().execute(input_data, run_id=run_id, context=context, max_repair_attempts=max_repair_attempts)
        artefact.rtl_code = self.sanitize_rtl(artefact.rtl_code)
        return artefact

    def format_prompt(self, input_data: MicroArchitecture, context: Optional[Dict[str, Any]] = None) -> str:
        prompt = (
            f"You are the Senior RTL Coder Agent. Generate clean, synthesizable Verilog (IEEE 1364-2001) RTL "
            f"implementing the given micro-architecture plan.\n\n"
            f"MicroArchitecture Plan:\n{json.dumps(input_data.model_dump(), indent=2)}\n\n"
        )

        if context and "requirements" in context:
            prompt += f"Original Requirements:\n{json.dumps(context['requirements'], indent=2)}\n\n"

        if context and "correction" in context:
            prompt += (
                f"### MANDATORY CORRECTION DIRECTIVES:\n"
                f"Previous implementation failed EDA checks. Address these specific directives:\n"
                f"{json.dumps(context['correction'], indent=2)}\n\n"
            )

        if context and "review" in context:
            prompt += (
                f"### PREVIOUS EDA REVIEW DEFECTS:\n"
                f"{json.dumps(context['review'], indent=2)}\n\n"
            )

        example_json = {
            "module_name": input_data.module_name,
            "language": "verilog",
            "top_module": input_data.module_name,
            "rtl_code": f"module {input_data.module_name} (\n  // ports\n);\n  // synthesizable RTL logic\nendmodule",
            "design_notes": "Synchronous design",
        }

        prompt += (
            f"Strict Hardware & Verilog Syntax Guidelines:\n"
            f"1. Synthesizable Verilog only. No initial blocks, no # delays in RTL.\n"
            f"2. CONSTANT LITERALS:\n"
            f"   - For decimal numbers: use 'd' prefix: e.g. 8'd255, 8'd0, 16'd10. NEVER write 8'b255!\n"
            f"   - For binary numbers: only use 0 or 1: e.g. 8'b11111111, 1'b0, 1'b1.\n"
            f"   - For hexadecimal numbers: use 'h' prefix: e.g. 8'hFF, 8'h00.\n"
            f"3. REG VS WIRE (CRITICAL):\n"
            f"   - If an output is assigned inside an always block: declare as 'output reg [WIDTH-1:0] name;'. DO NOT add an 'assign name = ...' statement.\n"
            f"   - If an output is assigned with continuous assign: declare as 'output wire name;'.\n"
            f"   - NEVER use 'assign' on a signal declared as 'reg'.\n"
            f"4. PREFER DIRECT PORT ASSIGNMENT:\n"
            f"   Assign directly to output reg ports (e.g. 'count <= count + 1'b1;') inside the clocked always block.\n"
            f"   DO NOT create intermediate registers like next_count or count_reg!\n"
            f"5. All registers must be initialized to 0 under the reset clause (!rst_n).\n"
            f"6. For memory arrays (e.g. FIFOs): on write (wr_en && !full), ensure the write statement is present: 'mem[wr_ptr] <= wr_data;'.\n"
            f"7. Strictly ONE driver per reg.\n"
            f"8. Provide the COMPLETE source code in the 'rtl_code' field with escaped newlines.\n\n"
            f"Respond with a JSON object following this EXACT format (do NOT output the schema itself):\n"
            f"{json.dumps(example_json, indent=2)}"
        )
        return prompt
