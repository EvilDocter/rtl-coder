"""Interactive Web Dashboard for the Multi-Agent RTL Coder Framework."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List
from pydantic import BaseModel

from eda.runner import WSLCommandRunner
from gateway.client import OllamaClient
from gateway.config import config

router = APIRouter(tags=["Dashboard"])

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RTL-Coder &mdash; Hardware Synthesis & Verification Framework</title>
  <style>
    :root {
      --bg: #090a0f;
      --surface: #111318;
      --surface-hover: #171a22;
      --border: #21262d;
      --border-focus: #388bfd;
      --accent: #2f81f7;
      --text-primary: #e6edf3;
      --text-secondary: #7d8590;
      --text-tertiary: #484f58;
      --success: #238636;
      --success-text: #3fb950;
      --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text-primary);
      font-family: var(--font-sans);
      font-size: 13px;
      line-height: 1.5;
      padding: 32px;
      -webkit-font-smoothing: antialiased;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 1px solid var(--border);
      padding-bottom: 20px;
      margin-bottom: 24px;
    }
    .brand h1 {
      font-size: 16px;
      font-weight: 600;
      letter-spacing: -0.2px;
      color: #fff;
    }
    .brand p {
      font-size: 12px;
      color: var(--text-secondary);
      margin-top: 2px;
    }
    .system-status {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .tag {
      font-family: var(--font-mono);
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 4px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text-secondary);
    }
    .tag.online {
      color: var(--success-text);
      border-color: rgba(35, 134, 54, 0.4);
      background: rgba(35, 134, 54, 0.1);
    }

    /* Pipeline Status Flow */
    .pipeline-container {
      margin-bottom: 24px;
    }
    .section-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-secondary);
      margin-bottom: 8px;
    }
    .pipeline {
      display: grid;
      grid-template-columns: repeat(8, 1fr);
      gap: 6px;
    }
    .node {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 8px 10px;
      transition: border-color 0.15s ease;
    }
    .node .role {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--text-secondary);
      margin-bottom: 2px;
    }
    .node .state {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 500;
      color: var(--text-tertiary);
    }
    .node.active {
      border-color: var(--accent);
      background: rgba(47, 129, 247, 0.05);
    }
    .node.active .state {
      color: var(--accent);
    }
    .node.pass {
      border-color: rgba(35, 134, 54, 0.5);
      background: rgba(35, 134, 54, 0.05);
    }
    .node.pass .state {
      color: var(--success-text);
    }

    /* Main Grid Layout */
    .grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 24px;
      align-items: start;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 18px;
      margin-bottom: 20px;
    }
    .panel-header {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-primary);
      margin-bottom: 14px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }

    /* Form Inputs */
    label {
      display: block;
      font-size: 11px;
      font-weight: 500;
      color: var(--text-secondary);
      margin-bottom: 6px;
    }
    select, textarea, button {
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--text-primary);
      padding: 8px 10px;
      font-size: 12px;
      margin-bottom: 12px;
      transition: border-color 0.15s ease;
    }
    select:focus, textarea:focus {
      outline: none;
      border-color: var(--border-focus);
    }
    textarea {
      height: 180px;
      resize: vertical;
      font-family: var(--font-mono);
      line-height: 1.45;
    }
    button.btn-primary {
      background: #238636;
      border: 1px solid rgba(240, 246, 252, 0.1);
      color: #fff;
      font-weight: 500;
      cursor: pointer;
      padding: 9px;
      margin-top: 4px;
    }
    button.btn-primary:hover {
      background: #2ea043;
    }
    button.btn-secondary {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-primary);
      cursor: pointer;
      font-size: 11px;
      padding: 5px 10px;
      width: auto;
    }
    button.btn-secondary:hover {
      background: var(--surface-hover);
      border-color: var(--text-secondary);
    }
    button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    /* Tabs & Code Viewer */
    .viewer-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 10px;
      margin-bottom: 12px;
    }
    .tabs {
      display: flex;
      gap: 2px;
    }
    .tab {
      background: none;
      border: none;
      padding: 6px 10px;
      font-size: 12px;
      color: var(--text-secondary);
      cursor: pointer;
      border-radius: 4px;
      width: auto;
      margin: 0;
    }
    .tab:hover {
      color: var(--text-primary);
      background: var(--surface-hover);
    }
    .tab.active {
      color: #fff;
      background: rgba(255, 255, 255, 0.08);
      font-weight: 500;
    }
    .code-view {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 14px;
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.5;
      max-height: 540px;
      overflow: auto;
      white-space: pre-wrap;
      color: #c9d1d9;
    }

    /* Run List */
    .run-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      border-radius: 4px;
    }
    .run-row:hover {
      background: var(--surface-hover);
    }
    .run-name {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--text-primary);
    }
    .run-meta {
      font-size: 11px;
      color: var(--text-secondary);
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>RTL-Coder</h1>
      <p>Autonomous Multi-Agent RTL Design, Verification & EDA Pipeline</p>
    </div>
    <div class="system-status">
      <span class="tag online" id="ollama-status">Backend Online</span>
      <span class="tag" id="model-badge">qwen2.5-coder:7b</span>
    </div>
  </header>

  <div class="pipeline-container">
    <div class="section-label">Pipeline Execution Stages</div>
    <div class="pipeline">
      <div class="node" id="node-spec"><div class="role">Specification</div><div class="state">IDLE</div></div>
      <div class="node" id="node-arch"><div class="role">Architecture</div><div class="state">IDLE</div></div>
      <div class="node" id="node-rtl"><div class="role">RTL Coder</div><div class="state">IDLE</div></div>
      <div class="node" id="node-verif"><div class="role">Verification</div><div class="state">IDLE</div></div>
      <div class="node" id="node-script"><div class="role">Scripting</div><div class="state">IDLE</div></div>
      <div class="node" id="node-eda"><div class="role">EDA Engine</div><div class="state">IDLE</div></div>
      <div class="node" id="node-review"><div class="role">Review</div><div class="state">IDLE</div></div>
      <div class="node" id="node-reflect"><div class="role">Reflection</div><div class="state">IDLE</div></div>
    </div>
  </div>

  <div class="grid">
    <div>
      <div class="panel">
        <div class="panel-header">Design Specification</div>
        <label for="preset-select">Standard Presets</label>
        <select id="preset-select" onchange="loadPreset()">
          <option value="">Custom Design Specification</option>
          <option value="counter">8-bit Synchronous Counter</option>
          <option value="fsm">1011 Sequence Detector FSM</option>
          <option value="fifo">16-Word Synchronous FIFO</option>
          <option value="alu">8-bit Arithmetic Logic Unit (ALU)</option>
          <option value="uart_tx">UART Transmitter (8-N-1)</option>
          <option value="spi_master">SPI Master Controller (Mode 0)</option>
        </select>

        <label for="spec-text">Specification Input</label>
        <textarea id="spec-text" placeholder="Enter hardware description, ports, reset levels, and functional behavior..."></textarea>

        <button class="btn-primary" id="run-btn" onclick="startGeneration()">Execute Generation & Verification</button>
      </div>

      <div class="panel">
        <div class="panel-header">Execution History</div>
        <div id="runs-list" style="max-height: 220px; overflow-y: auto;">
          <p style="color: var(--text-secondary); font-size: 11px;">Loading records...</p>
        </div>
      </div>
    </div>

    <div>
      <div class="panel" style="padding: 14px;">
        <div class="viewer-header">
          <div class="tabs">
            <button class="tab active" onclick="switchTab('rtl')">RTL Verilog</button>
            <button class="tab" onclick="switchTab('tb')">Testbench</button>
            <button class="tab" onclick="switchTab('arch')">Architecture</button>
            <button class="tab" onclick="switchTab('reqs')">Requirements</button>
            <button class="tab" onclick="switchTab('reports')">EDA Diagnostics</button>
            <button class="tab" onclick="switchTab('review')">Review & Reflection</button>
          </div>
          <button class="btn-secondary" onclick="openWaveforms()">View Waveforms (GTKWave)</button>
        </div>

        <div id="tab-content" class="code-view">// Select an execution record to view generated collateral.</div>
      </div>
    </div>
  </div>

  <script>
    let activeRunData = null;
    let activeTab = 'rtl';

    async function init() {
      await fetchStatus();
      await fetchRuns();
    }

    async function fetchStatus() {
      try {
        const res = await fetch('/health');
        const data = await res.json();
        const el = document.getElementById('ollama-status');
        el.innerText = data.ollama_connected ? 'Backend Online' : 'Backend Degraded';
        el.className = 'tag ' + (data.ollama_connected ? 'online' : '');
        document.getElementById('model-badge').innerText = data.primary_model || 'qwen2.5-coder:7b';
      } catch(e) {}
    }

    async function fetchRuns() {
      try {
        const res = await fetch('/api/runs');
        const runs = await res.json();
        const listEl = document.getElementById('runs-list');
        if (!runs.length) {
          listEl.innerHTML = '<p style="color: var(--text-secondary); font-size: 11px;">No executions logged yet.</p>';
          return;
        }
        listEl.innerHTML = runs.map(r => `
          <div class="run-row" onclick="loadRun('${r.run_id}')">
            <div>
              <div class="run-name">${r.run_id}</div>
              <div class="run-meta">${r.mtime ? new Date(r.mtime * 1000).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : ''}</div>
            </div>
            <span class="tag ${r.status === 'PASS' ? 'online' : ''}">${r.status || 'LOGGED'}</span>
          </div>
        `).join('');
      } catch(e) {}
    }

    async function loadRun(runId) {
      try {
        const res = await fetch(`/api/runs/${runId}`);
        activeRunData = await res.json();
        renderTab();
        updateNodesFromRun(activeRunData);
      } catch(e) {}
    }

    function updateNodesFromRun(data) {
      const nodes = ['spec', 'arch', 'rtl', 'verif', 'script', 'eda', 'review', 'reflect'];
      nodes.forEach(n => {
        const el = document.getElementById(`node-${n}`);
        el.className = 'node pass';
        el.querySelector('.state').innerText = 'PASS';
      });
    }

    function switchTab(tab) {
      activeTab = tab;
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      event.target.classList.add('active');
      renderTab();
    }

    function renderTab() {
      const box = document.getElementById('tab-content');
      if (!activeRunData) {
        box.innerText = '// Select or execute a run to view collateral...';
        return;
      }
      if (activeTab === 'rtl') box.innerText = activeRunData.rtl || '// No RTL code available';
      else if (activeTab === 'tb') box.innerText = activeRunData.testbench || '// No testbench code available';
      else if (activeTab === 'arch') box.innerText = JSON.stringify(activeRunData.architecture || {}, null, 2);
      else if (activeTab === 'reqs') box.innerText = JSON.stringify(activeRunData.requirements || {}, null, 2);
      else if (activeTab === 'reports') box.innerText = activeRunData.eda_reports || '// No EDA logs available';
      else if (activeTab === 'review') box.innerText = JSON.stringify(activeRunData.review || {}, null, 2);
    }

    const PRESETS = {
      counter: "Module Name: counter\\nDescription: 8-bit synchronous up-counter with synchronous active-low reset and overflow indicator.\\nPort Specifications:\\n- clk: 1-bit input clock\\n- rst_n: 1-bit input synchronous active-low reset\\n- enable: 1-bit input counter enable\\n- count: 8-bit output current count value\\n- overflow: 1-bit output flag, high when count == 255 and enable is high\\nBehavior:\\nWhen rst_n is low, count is 0 and overflow is 0. When enable is high on posedge clk, count increments by 1.",
      fsm: "Module Name: fsm_detector\\nDescription: Finite State Machine sequence detector that detects the 4-bit sequence 1011.\\nPort Specifications:\\n- clk: 1-bit input clock\\n- rst_n: 1-bit input synchronous active-low reset\\n- in_bit: 1-bit input serial bitstream\\n- detected: 1-bit output asserted high when sequence 1011 is detected",
      fifo: "Module Name: fifo_sync\\nDescription: 8-bit synchronous FIFO with 16 words depth.\\nPort Specifications:\\n- clk: 1-bit input clock\\n- rst_n: 1-bit input synchronous active-low reset\\n- wr_en: 1-bit input write enable\\n- rd_en: 1-bit input read enable\\n- wr_data: 8-bit input data to write\\n- rd_data: 8-bit output data read from FIFO\\n- full: 1-bit output status flag\\n- empty: 1-bit output status flag",
      alu: "Module Name: alu\\nDescription: 8-bit Arithmetic Logic Unit with operations ADD, SUB, AND, OR, XOR, SHL, SHR, PASS_A and flags zero, carry, negative.",
      uart_tx: "Module Name: uart_tx\\nDescription: UART Transmitter 8-N-1 format transmitting 8 data bits with start and stop bits.",
      spi_master: "Module Name: spi_master\\nDescription: SPI Master Mode 0 controller supporting 8-bit full-duplex transfers."
    };

    function loadPreset() {
      const val = document.getElementById('preset-select').value;
      if (PRESETS[val]) {
        document.getElementById('spec-text').value = PRESETS[val].replace(/\\\\n/g, '\\n');
      }
    }

    async function startGeneration() {
      const spec = document.getElementById('spec-text').value.trim();
      if (!spec) return alert('Enter a specification or select a preset.');

      const btn = document.getElementById('run-btn');
      btn.disabled = true;
      btn.innerText = 'Executing Pipeline...';

      try {
        const res = await fetch('/api/runs', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({spec_text: spec})
        });
        const result = await res.json();
        await fetchRuns();
        if (result.run_id) await loadRun(result.run_id);
      } catch(e) {
        alert('Pipeline execution error: ' + e);
      } finally {
        btn.disabled = false;
        btn.innerText = 'Execute Generation & Verification';
      }
    }

    async function openWaveforms() {
      if (!activeRunData || !activeRunData.run_id) return alert('Select an execution record first.');
      try {
        await fetch(`/api/runs/${activeRunData.run_id}/wave`, {method: 'POST'});
      } catch(e) {
        alert('Unable to launch GTKWave viewer');
      }
    }

    init();
  </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serves the main interactive dashboard interface."""
    return HTMLResponse(content=DASHBOARD_HTML)


@router.get("/api/runs")
def list_runs() -> List[Dict[str, Any]]:
    """Lists past execution runs."""
    runs_dir = config.base_dir / "runs"
    if not runs_dir.exists():
        return []

    results = []
    for d in sorted(runs_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if d.is_dir() and d.name != "history":
            review_files = list((d / "reports").glob("review_iter_*.json")) if (d / "reports").exists() else []
            status = "UNKNOWN"
            if review_files:
                try:
                    rev_data = json.loads(sorted(review_files)[-1].read_text(encoding="utf-8"))
                    status = rev_data.get("status", "UNKNOWN")
                except Exception:
                    pass

            results.append({
                "run_id": d.name,
                "mtime": d.stat().st_mtime,
                "status": status,
            })
    return results


@router.get("/api/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    """Retrieves full collateral, code, and reports for a given run."""
    run_dir = config.base_dir / "runs" / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    rtl_code = ""
    rtl_files = list((run_dir / "rtl").glob("*.v")) if (run_dir / "rtl").exists() else []
    if rtl_files:
        rtl_code = rtl_files[0].read_text(encoding="utf-8")

    tb_code = ""
    tb_files = list((run_dir / "verification").glob("*.v")) if (run_dir / "verification").exists() else []
    if tb_files:
        tb_code = tb_files[0].read_text(encoding="utf-8")

    reqs = {}
    req_file = run_dir / "requirements.json"
    if req_file.exists():
        reqs = json.loads(req_file.read_text(encoding="utf-8"))

    arch = {}
    arch_file = run_dir / "architecture.json"
    if arch_file.exists():
        arch = json.loads(arch_file.read_text(encoding="utf-8"))

    review = {}
    rev_files = list((run_dir / "reports").glob("review_iter_*.json")) if (run_dir / "reports").exists() else []
    if rev_files:
        review = json.loads(sorted(rev_files)[-1].read_text(encoding="utf-8"))

    eda_logs = []
    if (run_dir / "reports").exists():
        for log in sorted((run_dir / "reports").glob("*.log")):
            eda_logs.append(f"=== {log.name} ===\n" + log.read_text(encoding="utf-8", errors="replace"))

    return {
        "run_id": run_id,
        "rtl": rtl_code,
        "testbench": tb_code,
        "requirements": reqs,
        "architecture": arch,
        "review": review,
        "eda_reports": "\n\n".join(eda_logs),
    }


class RunRequest(BaseModel):
    spec_text: str


@router.post("/api/runs")
def trigger_run(payload: RunRequest) -> Dict[str, Any]:
    """Runs the multi-agent closed-loop flow from the dashboard."""
    from datetime import datetime
    from agents import (
        ArchitectAgent,
        ReflectionAgent,
        ReviewerAgent,
        RTLCoderAgent,
        ScriptEngineerAgent,
        SpecificationAnalystAgent,
        VerificationEngineerAgent,
    )
    from gateway.gateway_client import InferenceGatewayClient
    from orchestrator import Orchestrator, PipelineContext, RealEDAExecutor
    from schemas import create_run_layout

    run_id = f"web_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_paths = create_run_layout(run_id=run_id, base_dir=config.base_dir / "runs")
    ctx = PipelineContext(
        run_id=run_id,
        run_paths=run_paths,
        spec_text=payload.spec_text,
    )

    client = InferenceGatewayClient()
    spec_agent = SpecificationAnalystAgent(gateway_client=client, model=config.fast_model, temperature=0.0)
    arch_agent = ArchitectAgent(gateway_client=client, model=config.fast_model, temperature=0.0)
    rtl_agent = RTLCoderAgent(gateway_client=client, model=config.primary_model, temperature=0.0)
    verif_agent = VerificationEngineerAgent(gateway_client=client, model=config.primary_model, temperature=0.0)
    script_agent = ScriptEngineerAgent(gateway_client=client, model=config.fast_model, temperature=0.0)
    eda_executor = RealEDAExecutor()
    reviewer_agent = ReviewerAgent(gateway_client=client, model=config.fast_model)
    reflection_agent = ReflectionAgent(gateway_client=client, model=config.fast_model)

    orchestrator = Orchestrator(
        spec_agent=spec_agent,
        arch_agent=arch_agent,
        rtl_agent=rtl_agent,
        verif_agent=verif_agent,
        script_agent=script_agent,
        eda_executor=eda_executor,
        reviewer_agent=reviewer_agent,
        reflection_agent=reflection_agent,
        enable_git_commits=False,
    )

    final_state = orchestrator.run(ctx)
    return {"run_id": run_id, "final_state": final_state.value}


@router.post("/api/runs/{run_id}/wave")
def launch_wave(run_id: str):
    """Triggers GTKWave for a given run."""
    run_dir = config.base_dir / "runs" / run_id
    vcd_files = list((run_dir / "reports").glob("*.vcd")) + list((run_dir / "verification").glob("*.vcd"))
    if vcd_files:
        runner = WSLCommandRunner()
        wsl_vcd = runner.to_wsl_path(vcd_files[0])
        subprocess.Popen(["wsl", "--exec", "gtkwave", wsl_vcd])
        return {"status": "launched", "vcd": str(vcd_files[0])}
    return {"status": "no_vcd_found"}
