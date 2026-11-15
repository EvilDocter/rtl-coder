"""Gateway Audit Logger for Run History and Traceability."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from gateway.config import config
from gateway.schemas import GenerateRequest, GenerateResponse


class GatewayAuditLogger:
    """Logs prompts, raw responses, metadata, and token usage to runs/<run_id>/history."""

    @staticmethod
    def log_generation(
        request: GenerateRequest,
        response: GenerateResponse,
        run_id: Optional[str] = None,
    ) -> Optional[Path]:
        active_run = run_id or request.run_id
        if active_run:
            target_dir = config.base_dir / "runs" / active_run / "history"
        else:
            target_dir = config.base_dir / "runs" / "history"

        target_dir.mkdir(parents=True, exist_ok=True)
        log_file = target_dir / "gateway_audit.jsonl"

        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": active_run,
            "agent_role": request.agent_role.value if request.agent_role else None,
            "model": response.model_used,
            "prompt": request.prompt,
            "system_prompt": request.system_prompt,
            "json_mode": request.json_mode,
            "temperature": request.temperature,
            "latency_ms": response.latency_ms,
            "tokens_evaluated": response.tokens_evaluated,
            "tokens_generated": response.tokens_generated,
            "retries_used": response.retries_used,
            "success": response.success,
            "parsed_content": response.content,
            "raw_content": response.raw_content,
            "error_message": response.error_message,
        }

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return log_file
        except Exception as e:
            print(f"[GatewayAuditLogger] Warning: Could not write audit log: {e}")
            return None
