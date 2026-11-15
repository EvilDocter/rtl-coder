"""Automated test suite for Phase 2: Local Inference Gateway."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gateway.client import OllamaClient
from gateway.config import config
from gateway.logger import GatewayAuditLogger
from gateway.prompts import PROMPTS_BY_ROLE, get_system_prompt
from gateway.schemas import AgentRole, GenerateRequest, GenerateResponse
from gateway.service import app


@pytest.fixture
def test_client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


def test_system_prompts_all_agents():
    """Verify that all 7 specialized agents defined in the synopsis have dedicated prompts."""
    expected_roles = [
        AgentRole.SPECIFICATION_ANALYST,
        AgentRole.ARCHITECT,
        AgentRole.RTL_CODER,
        AgentRole.VERIFICATION_ENGINEER,
        AgentRole.SCRIPT_ENGINEER,
        AgentRole.REVIEWER,
        AgentRole.REFLECTION,
    ]
    for role in expected_roles:
        prompt = get_system_prompt(role)
        assert len(prompt) > 50, f"Prompt for {role} is unexpectedly short"
        assert "JSON" in prompt, f"Prompt for {role} must demand structured JSON"


def test_json_extraction_and_repair():
    """Verify extraction of raw JSON, markdown-wrapped JSON, and embedded JSON."""
    client = OllamaClient()

    # Direct JSON
    ok, data = client.extract_and_parse_json('{"module": "counter", "width": 8}')
    assert ok
    assert data["module"] == "counter"

    # Markdown wrapped ```json ... ```
    md_text = """Here is your output:
    ```json
    {
      "module": "fifo",
      "depth": 16
    }
    ```
    Hope this helps!"""
    ok, data = client.extract_and_parse_json(md_text)
    assert ok
    assert data["module"] == "fifo"
    assert data["depth"] == 16

    # Malformed text
    ok, data = client.extract_and_parse_json("This is purely invalid text with no json")
    assert not ok


def test_fastapi_health_endpoint(test_client):
    """Verify GET /health returns expected structure."""
    with patch.object(OllamaClient, "check_health", return_value=(True, ["qwen2.5-coder:1.5b"])):
        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["ollama_connected"] is True
        assert "qwen2.5-coder:1.5b" in data["available_models"]


def test_fastapi_generate_mocked(test_client):
    """Verify POST /generate receives structured request and returns typed GenerateResponse."""
    mock_response = GenerateResponse(
        success=True,
        content={"status": "ready", "module_name": "alu"},
        raw_content='{"status": "ready", "module_name": "alu"}',
        model_used="qwen2.5-coder:1.5b",
        latency_ms=120.5,
        tokens_evaluated=45,
        tokens_generated=30,
        retries_used=0,
    )

    with patch.object(OllamaClient, "generate", return_value=mock_response):
        payload = {
            "prompt": "Design an 8-bit adder",
            "agent_role": "rtl_coder",
            "json_mode": True,
            "temperature": 0.2,
        }
        resp = test_client.post("/generate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["content"]["module_name"] == "alu"
        assert data["latency_ms"] == 120.5


def test_gateway_audit_logging(tmp_path: Path):
    """Verify that generation requests and responses are written to the run history log."""
    with patch.object(config, "base_dir", tmp_path):
        req = GenerateRequest(
            prompt="Analyze UART requirements",
            agent_role=AgentRole.SPECIFICATION_ANALYST,
            run_id="run_test_audit",
        )
        resp = GenerateResponse(
            success=True,
            content={"module": "uart_rx"},
            raw_content='{"module": "uart_rx"}',
            model_used="qwen2.5-coder:1.5b",
            latency_ms=250.0,
            tokens_evaluated=10,
            tokens_generated=15,
            retries_used=0,
        )

        log_path = GatewayAuditLogger.log_generation(req, resp, run_id="run_test_audit")
        assert log_path is not None
        assert log_path.exists()

        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["run_id"] == "run_test_audit"
        assert entry["parsed_content"]["module"] == "uart_rx"


@pytest.mark.skipif(
    not OllamaClient().check_health()[0],
    reason="Local Ollama daemon is not running on http://127.0.0.1:11434"
)
def test_live_local_inference_structured_output():
    """Phase 2 Acceptance Test: gets a valid structured JSON response from the local model."""
    client = OllamaClient()
    connected, models = client.check_health()
    if not connected:
        pytest.skip("Ollama not connected")

    # Use fast model (1.5b) for speedy unit test execution
    chosen_model = config.fast_model if config.fast_model in models else models[0]

    req = GenerateRequest(
        prompt='Identify module name and bit width for a 4-bit synchronous up-counter. Respond in JSON with keys "module_name" and "width_bits".',
        agent_role=AgentRole.SPECIFICATION_ANALYST,
        model=chosen_model,
        json_mode=True,
        temperature=0.1,
        run_id="smoke_run_phase2",
    )

    resp = client.generate(req)
    assert resp.success is True, f"Generation failed: {resp.error_message}"
    assert isinstance(resp.content, dict), f"Expected dict, got {type(resp.content)}"
    assert "module_name" in resp.content or "width_bits" in resp.content
    assert resp.tokens_generated is not None and resp.tokens_generated > 0
    assert resp.latency_ms > 0
