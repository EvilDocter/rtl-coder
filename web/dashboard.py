"""Interactive Web Dashboard for the Multi-Agent RTL Coder Framework."""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from eda.runner import WSLCommandRunner
from gateway.client import OllamaClient
from gateway.config import config
from knowledge import HARDWARE_PATTERNS

router = APIRouter(tags=["Dashboard"])

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RTL-Coder: Multi-Agent AI Hardware Framework</title>
  <style>
    :root {
      --bg: #0d1117;
      --card: #161b22;
      --border: #30363d;
      --accent: #58a6ff;
      --success: #238636;
      --danger: #da3633;
      --warning: #d29922;
      --text: #c9d1d9;
      --text-muted: #8b949e;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
    body { background-color: var(--bg); color: var(--text); padding: 24px; }
    header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }
    h1 { font-size: 22px; color: #fff; display: flex; align-items: center; gap: 10px; }
    .badge { padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; text-transform: uppercase; }
    .badge-online { background: #23863633; color: #3fb950; border: 1px solid #238636; }
    .badge-model { background: #1f6feb33; color: #58a6ff; border: 1px solid #1f6feb; }
    
    .grid { display: grid; grid-template-columns: 380px 1fr; gap: 24px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 18px; margin-bottom: 20px; }
    .card h2 { font-size: 15px; color: #fff; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; }
    
    label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 6px; font-weight: 600; }
    select, textarea, input, button { width: 100%; background: #0d1117; border: 1px solid var(--border); border-radius: 6px; color: #fff; padding: 10px; margin-bottom: 12px; font-size: 13px; }
    textarea { height: 160px; resize: vertical; line-height: 1.4; font-family: monospace; }
    button { background: #238636; border: none; cursor: pointer; font-weight: 600; transition: 0.2s; padding: 12px; margin-top: 6px; }
    button:hover { background: #2ea043; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }

    /* Pipeline Status Flow */
    .pipeline { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
    .agent-node { flex: 1; min-width: 110px; padding: 10px; border: 1px solid var(--border); border-radius: 6px; background: #0d1117; text-align: center; }
    .agent-node .role { font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; }
    .agent-node .status { font-size: 12px; font-weight: 600; color: #8b949e; }
    .agent-node.active { border-color: var(--accent); background: #388bfd11; }
    .agent-node.active .status { color: var(--accent); }
    .agent-node.pass { border-color: #3fb950; background: #23863611; }
    .agent-node.pass .status { color: #3fb950; }

    /* Tabs */
    .tab-nav { display: flex; border-bottom: 1px solid var(--border); margin-bottom: 14px; gap: 4px; }
    .tab-btn { background: none; border: none; padding: 8px 14px; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; width: auto; font-size: 13px; }
    .tab-btn.active { color: #fff; border-bottom: 2px solid var(--accent); font-weight: 600; }
    .code-box { background: #090d13; border: 1px solid var(--border); border-radius: 6px; padding: 14px; font-family: Consolas, monospace; font-size: 12px; line-height: 1.4; max-height: 480px; overflow: auto; white-space: pre-wrap; }
    
    .run-item { padding: 10px; border-bottom: 1px solid var(--border); cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
    .run-item:hover { background: #1f242c; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>⚡ RTL-Coder Multi-Agent Hardware Framework</h1>
      <p style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Local, Privacy-Preserving Closed-Loop Hardware Design, Verification & EDA Automation</p>
    </div>
    <div style="display: flex; gap: 8px;">
      <span class="badge badge-online" id="ollama-status">Ollama Online</span>
      <span class="badge badge-model" id="model-badge">qwen2.5-coder:7b</span>
    </div>
  </header>

  <div class="pipeline">
    <div class="agent-node" id="node-spec"><div class="role">Spec Analyst</div><div class="status">IDLE</div></div>
    <div class="agent-node" id="node-arch"><div class="role">Architect</div><div class="status">IDLE</div></div>
    <div class="agent-node" id="node-rtl"><div class="role">RTL Coder</div><div class="status">IDLE</div></div>
    <div class="agent-node" id="node-verif"><div class="role">Verif Eng</div><div class="status">IDLE</div></div>
    <div class="agent-node" id="node-script"><div class="role">Script Eng</div><div class="status">IDLE</div></div>
    <div class="agent-node" id="node-eda"><div class="role">EDA Engine</div><div class="status">IDLE</div></div>
    <div class="agent-node" id="node-review"><div class="role">Reviewer</div><div class="status">IDLE</div></div>
    <div class="agent-node" id="node-reflect"><div class="role">Reflection</div><div class="status">IDLE</div></div>
  </div>

  <div class="grid">
    <!-- Left Column: Controls & Presets -->
    <div>
      <div class="card">
        <h2>Design Specification</h2>
        <label>Preset Hardware Modules</label>
        <select id="preset-select" onchange="loadPreset()">
          <option value="">-- Custom Specification --</option>
          <option value="counter">8-bit Synchronous Counter</option>
          <option value="fsm">1011 Sequence Detector FSM</option>
          <option value="fifo">16-Word Synchronous FIFO</option>
          <option value="alu">8-bit Arithmetic Logic Unit (ALU)</option>
          <option value="uart_tx">UART Transmitter (8-N-1)</option>
          <option value="spi_master">SPI Master Mode 0 Controller</option>
        </select>

        <label>Specification Text</label>
        <textarea id="spec-text" placeholder="Describe the digital hardware module, ports, clocks, active levels, and operations..."></textarea>

        <button id="run-btn" onclick="startGeneration()">⚡ Run Multi-Agent Closed Loop</button>
      </div>

      <div class="card">
        <h2>Past Execution Runs</h2>
        <div id="runs-list" style="max-height: 240px; overflow-y: auto;">
          <p style="color: var(--text-muted); font-size: 12px;">Loading past runs...</p>
        </div>
      </div>
    </div>

    <!-- Right Column: Collateral & Verification Viewer -->
    <div>
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div class="tab-nav">
            <button class="tab-btn active" onclick="switchTab('rtl')">RTL Verilog</button>
            <button class="tab-btn" onclick="switchTab('tb')">Testbench</button>
            <button class="tab-btn" onclick="switchTab('arch')">Architecture</button>
            <button class="tab-btn" onclick="switchTab('reqs')">Requirements</button>
            <button class="tab-btn" onclick="switchTab('reports')">EDA Reports</button>
            <button class="tab-btn" onclick="switchTab('review')">Review & Reflection</button>
          </div>
          <button style="width: auto; padding: 6px 14px; font-size: 12px; margin-bottom: 14px; background: #1f6feb;" onclick="openWaveforms()">📈 Open GTKWave</button>
        </div>

        <div id="tab-content" class="code-box">// Collateral will appear here upon generation...</div>
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
        document.getElementById('ollama-status').innerText = data.ollama_connected ? 'Ollama Online' : 'Ollama Offline';
        document.getElementById('model-badge').innerText = data.primary_model || 'qwen2.5-coder:7b';
      } catch(e) {}
    }

    async function fetchRuns() {
      try {
        const res = await fetch('/api/runs');
        const runs = await res.json();
        const listEl = document.getElementById('runs-list');
        if (!runs.length) {
          listEl.innerHTML = '<p style="color: var(--text-muted); font-size: 12px;">No runs yet.</p>';
          return;
        }
        listEl.innerHTML = runs.map(r => `
          <div class="run-item" onclick="loadRun('${r.run_id}')">
            <div>
              <div style="font-weight: 600; font-size: 13px;">${r.run_id}</div>
              <div style="font-size: 11px; color: var(--text-muted);">${r.mtime}</div>
            </div>
            <span class="badge ${r.status === 'PASS' ? 'badge-online' : 'badge-model'}">${r.status || 'DONE'}</span>
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
        el.className = 'agent-node pass';
        el.querySelector('.status').innerText = 'PASS';
      });
    }

    function switchTab(tab) {
      activeTab = tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      event.target.classList.add('active');
      renderTab();
    }

    function renderTab() {
      const box = document.getElementById('tab-content');
      if (!activeRunData) {
        box.innerText = '// Select or execute a run to view collateral...';
        return;
      }
      if (activeTab === 'rtl') box.innerText = activeRunData.rtl || '// No RTL code';
      else if (activeTab === 'tb') box.innerText = activeRunData.testbench || '// No testbench code';
      else if (activeTab === 'arch') box.innerText = JSON.stringify(activeRunData.architecture || {}, null, 2);
      else if (activeTab === 'reqs') box.innerText = JSON.stringify(activeRunData.requirements || {}, null, 2);
      else if (activeTab === 'reports') box.innerText = activeRunData.eda_reports || '// No EDA reports';
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
      if (!spec) return alert('Please enter a specification or select a preset!');

      const btn = document.getElementById('run-btn');
      btn.disabled = true;
      btn.innerText = '⏳ Agents Designing & Verifying...';

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
        alert('Generation failed: ' + e);
      } finally {
        btn.disabled = false;
        btn.innerText = '⚡ Run Multi-Agent Closed Loop';
      }
    }

    async function openWaveforms() {
      if (!activeRunData || !activeRunData.run_id) return alert('Select a run first!');
      try {
        await fetch(`/api/runs/${activeRunData.run_id}/wave`, {method: 'POST'});
      } catch(e) {
        alert('Failed to launch waveform viewer');
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
