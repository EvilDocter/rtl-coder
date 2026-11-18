"""Reflection Agent implementation."""

import json
from typing import Any, Dict, Optional
from agents.base_agent import BaseAgent
from gateway.gateway_client import InferenceGatewayClient
from gateway.schemas import AgentRole
from schemas.hardware import CorrectionTask, FaultClassification


class ReflectionAgent(BaseAgent[Dict[str, Any], CorrectionTask]):
    """Analyzes EDA failures, identifies root causes, and issues targeted correction tasks."""

    def __init__(
        self,
        gateway_client: Optional[InferenceGatewayClient] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ):
        super().__init__(
            role=AgentRole.REFLECTION,
            output_schema=CorrectionTask,
            gateway_client=gateway_client,
            model=model,
            temperature=temperature,
        )

    def format_prompt(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
        example_task = {
            "root_cause_analysis": "Summary of failure root cause from EDA diagnostics",
            "target_agent": "rtl_coder",
            "fault_classification": "RTL_BUG",
            "specific_corrections": [
                "Detailed correction directive 1",
                "Detailed correction directive 2"
            ],
            "requires_human_escalation": False,
            "escalation_reason": None
        }
        prompt = (
            f"You are the Reflection and Error Diagnosis Agent. Analyze these EDA failure reports and determine "
            f"the exact root cause and target agent responsible for fixing the defect.\n\n"
            f"Review Finding & Defect Log:\n{json.dumps(input_data, indent=2)}\n\n"
            f"Guidelines:\n"
            f"1. Accurately assign blame:\n"
            f"   - If simulation failed with 'got x' or 'unknown' or output is unassigned, this is an **RTL_BUG**! Set 'target_agent': 'rtl_coder'.\n"
            f"   - If compilation or linting failed, this is an **RTL_BUG**! Set 'target_agent': 'rtl_coder'.\n"
            f"   - Only set 'verification_engineer' if the RTL is verified correct but the testbench assertions/stimulus had wrong expected numbers.\n"
            f"2. Provide concrete, actionable lines/changes in 'specific_corrections'.\n"
            f"Respond with a JSON object following this EXACT format (do NOT output the schema itself):\n"
            f"{json.dumps(example_task, indent=2)}"
        )
        return prompt
