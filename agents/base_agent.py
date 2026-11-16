"""Base Agent Class with schema enforcement, gateway routing, and self-repair."""

import json
from typing import Any, Dict, Generic, Optional, Type, TypeVar, Union
from pydantic import BaseModel, ValidationError

from gateway.gateway_client import InferenceGatewayClient
from gateway.prompts import get_system_prompt
from gateway.schemas import AgentRole, GenerateResponse

InputT = TypeVar("InputT", bound=Union[BaseModel, str, Dict[str, Any]])
OutputT = TypeVar("OutputT", bound=BaseModel)


class BaseAgent(Generic[InputT, OutputT]):
    """Base class for all 7 specialized agents in the framework."""

    def __init__(
        self,
        role: AgentRole,
        output_schema: Type[OutputT],
        system_prompt: Optional[str] = None,
        gateway_client: Optional[InferenceGatewayClient] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
    ):
        self.role = role
        self.output_schema = output_schema
        self.system_prompt = system_prompt or get_system_prompt(role)
        self.gateway_client = gateway_client or InferenceGatewayClient()
        self.model = model
        self.temperature = temperature

    def format_prompt(self, input_data: InputT, context: Optional[Dict[str, Any]] = None) -> str:
        """Serializes input data into an LLM prompt string."""
        if isinstance(input_data, BaseModel):
            data_str = json.dumps(input_data.model_dump(), indent=2)
        elif isinstance(input_data, dict):
            data_str = json.dumps(input_data, indent=2)
        else:
            data_str = str(input_data)

        prompt = f"### Input Data:\n{data_str}\n"

        if context:
            prompt += f"\n### Context & Constraints:\n{json.dumps(context, indent=2)}\n"

        schema_json = json.dumps(self.output_schema.model_json_schema(), indent=2)
        prompt += (
            f"\n### Required JSON Output Schema:\n{schema_json}\n"
            f"Produce strictly valid JSON conforming exactly to the above schema."
        )
        return prompt

    def execute(
        self,
        input_data: InputT,
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        max_repair_attempts: int = 2,
    ) -> OutputT:
        """Executes the agent task through the inference gateway with Pydantic validation."""
        prompt = self.format_prompt(input_data, context=context)

        for attempt in range(max_repair_attempts + 1):
            response: GenerateResponse = self.gateway_client.generate(
                prompt=prompt,
                agent_role=self.role,
                system_prompt=self.system_prompt,
                model=self.model,
                json_mode=True,
                temperature=self.temperature,
                run_id=run_id,
            )

            if not response.success:
                if attempt == max_repair_attempts:
                    raise RuntimeError(f"Agent {self.role.value} failed: {response.error_message}")
                prompt = (
                    f"{prompt}\n\n"
                    f"CRITICAL ERROR: Previous call failed: {response.error_message}. "
                    f"Regenerate the response adhering strictly to the required schema."
                )
                continue

            # Validate against Pydantic model
            try:
                if isinstance(response.content, dict):
                    return self.output_schema(**response.content)
                elif isinstance(response.content, str):
                    raw_dict = json.loads(response.content)
                    return self.output_schema(**raw_dict)
                else:
                    raise ValueError(f"Unexpected content type: {type(response.content)}")
            except (ValidationError, Exception) as val_err:
                if attempt == max_repair_attempts:
                    raise RuntimeError(
                        f"Agent {self.role.value} output schema validation failed after "
                        f"{max_repair_attempts} repair attempts: {str(val_err)}"
                    )
                # Formulate targeted repair prompt
                prompt = (
                    f"{prompt}\n\n"
                    f"CRITICAL VALIDATION ERROR: The produced JSON had schema errors:\n{str(val_err)}\n"
                    f"Fix every listed error and produce valid JSON strictly conforming to the schema."
                )

        raise RuntimeError(f"Agent {self.role.value} failed to produce valid output.")
