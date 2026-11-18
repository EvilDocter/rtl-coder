"""Hardware Architect Agent implementation."""

import json
from typing import Any, Dict, Optional
from agents.base_agent import BaseAgent
from gateway.gateway_client import InferenceGatewayClient
from gateway.schemas import AgentRole
from schemas.hardware import MicroArchitecture, Requirements


class ArchitectAgent(BaseAgent[Requirements, MicroArchitecture]):
    """Transforms structured Requirements into a machine-actionable micro-architecture plan."""

    def __init__(
        self,
        gateway_client: Optional[InferenceGatewayClient] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ):
        super().__init__(
            role=AgentRole.ARCHITECT,
            output_schema=MicroArchitecture,
            gateway_client=gateway_client,
            model=model,
            temperature=temperature,
        )

    def format_prompt(self, input_data: Requirements, context: Optional[Dict[str, Any]] = None) -> str:
        summary_text = (input_data.summary or "").lower()
        reqs_text = " ".join(input_data.functional_requirements).lower()
        mod_name = input_data.module_name.lower()

        is_fsm = "fsm" in mod_name or "fsm" in summary_text or "sequence" in summary_text or "fsm" in reqs_text
        is_fifo = "fifo" in mod_name or "fifo" in summary_text
        is_counter = "counter" in mod_name or "counter" in summary_text or "count" in summary_text

        if is_fsm:
            example_arch = {
                "module_name": input_data.module_name,
                "architecture_overview": f"Finite State Machine microarchitecture for {input_data.module_name}",
                "internal_registers": [
                    {"name": "state", "width_bits": 3, "reset_value": "0", "description": "Current state register"}
                ],
                "internal_signals": [],
                "fsm_states": [
                    {"state_name": "S_IDLE", "encoding": "3'd0", "transitions": [{"condition": "in_bit == 1", "to_state": "S_1"}]},
                    {"state_name": "S_1", "encoding": "3'd1", "transitions": [{"condition": "in_bit == 0", "to_state": "S_10"}]}
                ],
                "datapath_blocks": [],
                "control_logic": ["Assert detected output when sequence pattern is matched"],
            }
        elif is_fifo:
            example_arch = {
                "module_name": input_data.module_name,
                "architecture_overview": f"Synchronous FIFO buffer with circular pointer tracking",
                "internal_registers": [
                    {"name": "wr_ptr", "width_bits": 4, "reset_value": "0", "description": "Write pointer"},
                    {"name": "rd_ptr", "width_bits": 4, "reset_value": "0", "description": "Read pointer"},
                    {"name": "count", "width_bits": 5, "reset_value": "0", "description": "Word counter (0 to 16)"}
                ],
                "internal_signals": [],
                "fsm_states": [],
                "datapath_blocks": [
                    {"name": "mem_array", "operation": "memory", "inputs": ["wr_data", "wr_ptr"], "outputs": ["rd_data", "rd_ptr"]}
                ],
                "control_logic": [
                    "assign empty = (count == 5'd0);",
                    "assign full = (count == 5'd16);"
                ],
            }
        elif is_counter:
            example_arch = {
                "module_name": input_data.module_name,
                "architecture_overview": f"Synchronous up-counter with direct register outputs",
                "internal_registers": [],
                "internal_signals": [],
                "fsm_states": [],
                "datapath_blocks": [],
                "control_logic": [
                    "Synchronous increment: on posedge clk when enable, count <= count + 1'b1",
                    "Overflow indicator: overflow <= (count == 8'd255) && enable"
                ],
            }
        else:
            example_arch = {
                "module_name": input_data.module_name,
                "architecture_overview": f"Microarchitecture plan for {input_data.module_name}",
                "internal_registers": [],
                "internal_signals": [],
                "fsm_states": [],
                "datapath_blocks": [],
                "control_logic": ["Direct assignment to output ports based on functional requirements"],
            }
        prompt = (
            f"You are the Lead Hardware Architect Agent. Transform the following hardware requirements "
            f"into an unambiguous micro-architecture plan before RTL code is written.\n\n"
            f"Requirements:\n{json.dumps(input_data.model_dump(), indent=2)}\n\n"
            f"Specify internal registers, reset values, internal signals, FSM states/transitions (if any), "
            f"datapaths, and control logic.\n"
            f"Respond with a JSON object following this EXACT format (do NOT output schema definition):\n"
            f"{json.dumps(example_arch, indent=2)}"
        )
        return prompt
