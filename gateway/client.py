"""Local Ollama Inference Client with Retries, JSON Repair, and Schema Validation."""

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
from gateway.config import config
from gateway.logger import GatewayAuditLogger
from gateway.prompts import get_system_prompt
from gateway.schemas import AgentRole, GenerateRequest, GenerateResponse


class OllamaClient:
    """Communicates directly with the local Ollama instance on http://127.0.0.1:11434."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or config.ollama_base_url).rstrip("/")

    def check_health(self) -> Tuple[bool, List[str]]:
        """Checks if local Ollama daemon is active and returns installed model names."""
        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    models_data = res.json().get("models", [])
                    model_names = [m.get("name", "") for m in models_data]
                    return True, model_names
        except Exception:
            pass
        return False, []

    @staticmethod
    def extract_and_parse_json(text: str) -> Tuple[bool, Union[Dict[str, Any], List[Any], str]]:
        """Robustly extracts and parses JSON even if wrapped in markdown code blocks."""
        cleaned = text.strip()

        # 1. Try direct parsing
        try:
            return True, json.loads(cleaned)
        except Exception:
            pass

        # 2. Extract from ```json ... ``` or ``` ... ```
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if code_block_match:
            candidate = code_block_match.group(1).strip()
            try:
                return True, json.loads(candidate)
            except Exception:
                pass

        # 3. Find outermost braces { ... } or brackets [ ... ]
        curly_match = re.search(r"(\{[\s\S]*\})", cleaned)
        if curly_match:
            try:
                return True, json.loads(curly_match.group(1))
            except Exception:
                pass

        bracket_match = re.search(r"(\[[\s\S]*\])", cleaned)
        if bracket_match:
            try:
                return True, json.loads(bracket_match.group(1))
            except Exception:
                pass

        return False, cleaned

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Executes local LLM generation with retries, timeout handling, and JSON validation."""
        model_name = request.model or config.primary_model
        system_prompt = request.system_prompt or get_system_prompt(request.agent_role)

        start_time = time.perf_counter()
        retries_used = 0
        current_prompt = request.prompt
        last_error: Optional[str] = None
        raw_response_text = ""
        prompt_tokens = 0
        completion_tokens = 0

        for attempt in range(config.max_retries):
            retries_used = attempt
            try:
                payload: Dict[str, Any] = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": current_prompt},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": request.temperature,
                    },
                }

                if request.json_mode:
                    payload["format"] = "json"

                with httpx.Client(timeout=config.request_timeout_seconds) as client:
                    http_resp = client.post(
                        f"{self.base_url}/api/chat",
                        json=payload,
                    )

                if http_resp.status_code != 200:
                    last_error = f"Ollama returned HTTP {http_resp.status_code}: {http_resp.text}"
                    time.sleep(1.0)
                    continue

                data = http_resp.json()
                raw_response_text = data.get("message", {}).get("content", "")
                prompt_tokens = data.get("prompt_eval_count", 0)
                completion_tokens = data.get("eval_count", 0)

                # Process Output
                if not request.json_mode:
                    latency_ms = (time.perf_counter() - start_time) * 1000.0
                    response = GenerateResponse(
                        success=True,
                        content=raw_response_text,
                        raw_content=raw_response_text,
                        model_used=model_name,
                        latency_ms=round(latency_ms, 2),
                        tokens_evaluated=prompt_tokens,
                        tokens_generated=completion_tokens,
                        retries_used=retries_used,
                    )
                    GatewayAuditLogger.log_generation(request, response)
                    return response

                # Attempt JSON parsing
                parsed_ok, parsed_data = self.extract_and_parse_json(raw_response_text)
                if parsed_ok:
                    latency_ms = (time.perf_counter() - start_time) * 1000.0
                    response = GenerateResponse(
                        success=True,
                        content=parsed_data,
                        raw_content=raw_response_text,
                        model_used=model_name,
                        latency_ms=round(latency_ms, 2),
                        tokens_evaluated=prompt_tokens,
                        tokens_generated=completion_tokens,
                        retries_used=retries_used,
                    )
                    GatewayAuditLogger.log_generation(request, response)
                    return response

                # If JSON parsing failed, construct repair prompt for retry
                last_error = f"Malformed JSON produced: {raw_response_text[:120]}..."
                current_prompt = (
                    f"{request.prompt}\n\n"
                    f"CRITICAL: Your previous response failed to parse as valid JSON. "
                    f"Produce STRICT, RAW, VALID JSON ONLY. Do not include markdown code blocks or explanations."
                )

            except httpx.TimeoutException:
                last_error = f"Request timed out after {config.request_timeout_seconds}s"
            except Exception as e:
                last_error = f"Inference client error: {str(e)}"

            time.sleep(1.0)

        # Retries exhausted
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        failed_response = GenerateResponse(
            success=False,
            content=raw_response_text,
            raw_content=raw_response_text,
            model_used=model_name,
            latency_ms=round(latency_ms, 2),
            tokens_evaluated=prompt_tokens,
            tokens_generated=completion_tokens,
            retries_used=retries_used,
            error_message=last_error or "Generation failed after max retries",
        )
        GatewayAuditLogger.log_generation(request, failed_response)
        return failed_response
