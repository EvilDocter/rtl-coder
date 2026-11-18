"""Reviewer Agent implementation."""

import json
from typing import Any, Dict, List, Optional
from agents.base_agent import BaseAgent
from eda.models import ToolReport, ToolStatus
from gateway.gateway_client import InferenceGatewayClient
from gateway.schemas import AgentRole
from schemas.hardware import DefectCategory, DefectSeverity, ReviewDefect, ReviewFinding


class ReviewerAgent(BaseAgent[Dict[str, Any], ReviewFinding]):
    """Analyzes EDA tool reports (lint, compile, sim, synth) and issues pass/fail rulings."""

    def __init__(
        self,
        gateway_client: Optional[InferenceGatewayClient] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ):
        super().__init__(
            role=AgentRole.REVIEWER,
            output_schema=ReviewFinding,
            gateway_client=gateway_client,
            model=model,
            temperature=temperature,
        )

    def execute(
        self,
        input_data: Dict[str, Any],
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        max_repair_attempts: int = 2,
    ) -> ReviewFinding:
        """Determines review status directly from objective EDA tool outputs.

        If all tools passed cleanly, outputs PASS immediately without unnecessary latency.
        If any tool failed, uses LLM reasoning to classify defect categories and root causes.
        """
        tool_reports: List[Dict[str, Any]] = input_data.get("tool_reports", [])

        # Check objective pass/fail
        all_passed = True
        compilation_clean = True
        simulation_clean = True
        lint_clean = True
        synthesis_clean = True
        defects: List[ReviewDefect] = []

        for r in tool_reports:
            stage = r.get("stage", "")
            status = r.get("status", "")
            messages = r.get("messages", [])

            if status != "PASS":
                all_passed = False
                if stage == "compile":
                    compilation_clean = False
                elif stage == "sim":
                    simulation_clean = False
                elif stage == "lint":
                    lint_clean = False
                elif stage == "synth":
                    synthesis_clean = False

            # Harvest parsed diagnostic messages
            for msg in messages:
                sev = msg.get("severity")
                if sev == "ERROR" or (sev == "WARNING" and status != "PASS"):
                    defects.append(
                        ReviewDefect(
                            category=DefectCategory.SYNTAX if stage in ["compile", "lint"] else DefectCategory.FUNCTIONAL,
                            severity=DefectSeverity.ERROR if (sev == "ERROR" or status != "PASS") else DefectSeverity.WARNING,
                            file=msg.get("file"),
                            line=msg.get("line"),
                            message=msg.get("message", f"Issue in {stage}"),
                        )
                    )

            # If tool failed but no message was parsed, capture stderr snippet
            if status != "PASS" and not any(d.message.startswith(f"[{stage}]") for d in defects):
                raw_err = r.get("stderr", "") or r.get("stdout", "")
                cleaned_err = [
                    line.strip() for line in raw_err.splitlines()
                    if "Failed to detect nested virtualization" not in line and line.strip()
                ]
                if cleaned_err:
                    first_err_line = cleaned_err[-1][:200]
                    defects.append(
                        ReviewDefect(
                            category=DefectCategory.SYNTAX if stage in ["compile", "lint"] else DefectCategory.FUNCTIONAL,
                            severity=DefectSeverity.ERROR,
                            message=f"[{stage}] {first_err_line}",
                        )
                    )

        if all_passed and len(defects) == 0:
            return ReviewFinding(
                status="PASS",
                summary="All EDA checks passed: lint, compile, simulation, and logic synthesis are 100% clean.",
                compilation_clean=True,
                simulation_clean=True,
                lint_clean=True,
                synthesis_clean=True,
                defects=[],
            )

        # If failures exist, run LLM to generate rich review summary
        try:
            return super().execute(input_data, run_id=run_id, context=context, max_repair_attempts=max_repair_attempts)
        except Exception:
            # Fallback to direct structured finding
            return ReviewFinding(
                status="FAIL",
                summary=f"EDA flow detected {len(defects)} defect(s) across stages.",
                compilation_clean=compilation_clean,
                simulation_clean=simulation_clean,
                lint_clean=lint_clean,
                synthesis_clean=synthesis_clean,
                defects=defects,
            )

    def format_prompt(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
        prompt = (
            f"You are the Senior EDA Verification Reviewer Agent. Analyze these tool reports and generate a structured "
            f"ReviewFinding assessment with classification of any defects.\n\n"
            f"EDA Reports:\n{json.dumps(input_data, indent=2)}\n\n"
            f"Respond with a JSON object following this EXACT schema:\n"
            f"{self.output_schema.model_json_schema()}"
        )
        return prompt
