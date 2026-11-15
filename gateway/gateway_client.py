"""Inference Gateway Client SDK for Agents."""

from typing import Any, Dict, Optional, Union
import httpx

from gateway.client import OllamaClient
from gateway.config import config
from gateway.schemas import AgentRole, GenerateRequest, GenerateResponse


class InferenceGatewayClient:
    """Client used by all 7 agents to call the local inference gateway.

    Operates in two modes:
    1. HTTP Mode: Sends requests to the running FastAPI gateway at http://127.0.0.1:8000.
    2. Direct In-Process Mode: If the HTTP gateway is not running, falls back
       directly to the local OllamaClient without disrupting the pipeline.
    """

    def __init__(self, gateway_url: Optional[str] = None):
        self.gateway_url = (gateway_url or f"http://{config.host}:{config.port}").rstrip("/")
        self._in_process_fallback = OllamaClient()

    def generate(
        self,
        prompt: str,
        agent_role: AgentRole = AgentRole.GENERIC,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        json_mode: bool = True,
        temperature: float = 0.2,
        run_id: Optional[str] = None,
    ) -> GenerateResponse:
        """Invokes the inference gateway to produce collateral."""
        req = GenerateRequest(
            prompt=prompt,
            agent_role=agent_role,
            system_prompt=system_prompt,
            model=model,
            json_mode=json_mode,
            temperature=temperature,
            run_id=run_id,
        )

        # 1. Try calling the HTTP service
        try:
            with httpx.Client(timeout=config.request_timeout_seconds) as client:
                res = client.post(f"{self.gateway_url}/generate", json=req.model_dump())
                if res.status_code == 200:
                    return GenerateResponse(**res.json())
        except Exception:
            pass

        # 2. Seamless fallback to in-process local client
        return self._in_process_fallback.generate(req)
