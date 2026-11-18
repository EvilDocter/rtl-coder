"""Specification Analyst Agent implementation."""

import json
from typing import Any, Dict, Optional
from agents.base_agent import BaseAgent
from gateway.gateway_client import InferenceGatewayClient
from gateway.schemas import AgentRole
from schemas.hardware import Requirements


class SpecificationAnalystAgent(BaseAgent[str, Requirements]):
    """Analyzes unstructured natural language specifications and outputs structured Requirements."""

    def __init__(
        self,
        gateway_client: Optional[InferenceGatewayClient] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ):
        super().__init__(
            role=AgentRole.SPECIFICATION_ANALYST,
            output_schema=Requirements,
            gateway_client=gateway_client,
            model=model,
            temperature=temperature,
        )

    def format_prompt(self, input_data: str, context: Optional[Dict[str, Any]] = None) -> str:
        example_reqs = {
            "module_name": "example_module",
            "summary": "Module summary",
            "clocking": {"clock_name": "clk", "edge": "posedge", "frequency_mhz": None},
            "resets": [{"signal_name": "rst_n", "active_level": "low", "type": "synchronous"}],
            "ports": [
                {"name": "clk", "direction": "input", "width_bits": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width_bits": 1, "description": "Active-low reset"},
                {"name": "out", "direction": "output", "width_bits": 8, "description": "Data output"},
            ],
            "parameters": [],
            "functional_requirements": ["Describe the primary functional operation specified in the text"],
            "corner_cases": ["Reset assertion during operation"],
        }
        prompt = (
            f"You are the Specification Analyst Agent. Analyze this hardware specification and extract a complete, "
            f"rigorous requirements document.\n\n"
            f"Specification Text:\n\"\"\"\n{input_data}\n\"\"\"\n\n"
            f"CRITICAL PORT EXTRACTION RULES:\n"
            f"1. Extract EVERY single signal mentioned in the Port Specifications without exception!\n"
            f"2. Do not omit any input, output, or flag signal (e.g. overflow, count, enable, full, empty, detected).\n"
            f"3. All ports must be present in the 'ports' array with exact name, direction, and width_bits.\n\n"
            f"Respond with a JSON object following this EXACT format (do NOT output schema definition):\n"
            f"{json.dumps(example_reqs, indent=2)}"
        )
        return prompt
