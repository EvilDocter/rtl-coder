"""EDA Script Engineer Agent implementation."""

import json
from typing import Any, Dict, Optional
from agents.base_agent import BaseAgent
from gateway.gateway_client import InferenceGatewayClient
from gateway.schemas import AgentRole
from schemas.hardware import EDAScriptArtefact


class ScriptEngineerAgent(BaseAgent[Dict[str, Any], EDAScriptArtefact]):
    """Generates automated EDA tool scripts for Yosys, Icarus Verilog, Verilator, and Makefiles."""

    def __init__(
        self,
        gateway_client: Optional[InferenceGatewayClient] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ):
        super().__init__(
            role=AgentRole.SCRIPT_ENGINEER,
            output_schema=EDAScriptArtefact,
            gateway_client=gateway_client,
            model=model,
            temperature=temperature,
        )

    def validate_script(self, script: EDAScriptArtefact) -> bool:
        """Validates that the generated script contains necessary tool commands."""
        content = script.script_content.lower()
        if script.tool == "yosys":
            return "read_verilog" in content and ("write_verilog" in content or "stat" in content)
        elif script.tool == "iverilog":
            return "iverilog" in content or "vvp" in content
        elif script.tool == "verilator":
            return "verilator" in content
        return True

    def format_prompt(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
        tool = input_data.get("tool", "yosys")
        top_module = input_data.get("top_module", "top")
        sources = input_data.get("sources", [f"{top_module}.v"])
        output_file = input_data.get("output_file", f"{top_module}_syn.v")

        if tool == "yosys":
            sources_str = " ".join(sources)
            example_artefact = {
                "tool": "yosys",
                "script_type": "tcl",
                "file_name": f"synth_{top_module}.ys",
                "script_content": (
                    f"read_verilog {sources_str}\n"
                    f"hierarchy -check -top {top_module}\n"
                    f"proc; opt; memory; opt; fsm; opt; techmap; opt;\n"
                    f"abc -g AND,NAND,OR,NOR,XOR,XNOR\n"
                    f"clean\n"
                    f"write_verilog -noattr {output_file}\n"
                    f"stat\n"
                ),
                "expected_outputs": [output_file],
            }
        elif tool == "iverilog":
            sources_str = " ".join(sources)
            example_artefact = {
                "tool": "iverilog",
                "script_type": "makefile",
                "file_name": "Makefile",
                "script_content": (
                    f"TOP = {top_module}\n"
                    f"SOURCES = {sources_str}\n\n"
                    f"all: sim\n\n"
                    f"sim:\n"
                    f"\tiverilog -o $(TOP).vvp $(SOURCES)\n"
                    f"\tvvp $(TOP).vvp\n\n"
                    f"clean:\n"
                    f"\trm -f $(TOP).vvp waves.vcd\n"
                ),
                "expected_outputs": [f"{top_module}.vvp"],
            }
        else:
            example_artefact = {
                "tool": tool,
                "script_type": "bash",
                "file_name": f"run_{tool}.sh",
                "script_content": f"#!/bin/bash\nset -e\necho 'Running {tool}'\n",
                "expected_outputs": [],
            }

        prompt = (
            f"You are the Senior EDA Script Engineer Agent. Generate an automated execution script "
            f"for tool '{tool}' targeting module '{top_module}'.\n\n"
            f"Task Parameters:\n{json.dumps(input_data, indent=2)}\n\n"
            f"Requirements:\n"
            f"1. Generate clean, robust, and reproducible script syntax.\n"
            f"2. Ensure all inputs are properly mapped and output destinations are preserved.\n"
            f"3. For Yosys: include read_verilog, hierarchy, synthesis passes (proc, opt, memory, techmap), stat, and write_verilog.\n"
            f"4. For Makefile: include default target, simulation run, and clean targets.\n\n"
            f"Respond with a JSON object following this EXACT format (do NOT output schema definition):\n"
            f"{json.dumps(example_artefact, indent=2)}"
        )
        return prompt
