"""Interactive Web Dashboard for the Multi-Agent RTL Coder Framework."""

from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
import json
from pathlib import Path
import subprocess
import threading
from typing import Any, Dict, List, Optional
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
  <title>RTL-Coder - Multi-Agent Hardware Synthesis & Verification Framework</title>
  <style>
    :root {
      --bg: #0b0f19;
      --surface: #111827;
      --surface-card: #162032;
      --surface-hover: #1e293b;
      --border: #1f293d;
      --border-bright: #334155;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.25);
      --success: #22c55e;
      --success-glow: rgba(34, 197, 94, 0.2);
      --warning: #f59e0b;
      --error: #ef4444;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --font-mono: ui-monospace, "SF Mono", Consolas, "Liberation Mono", Menlo, monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text-primary);
      font-family: var(--font-sans);
      font-size: 13px;
      line-height: 1.5;
      padding: 24px 32px;
      -webkit-font-smoothing: antialiased;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 18px;
      margin-bottom: 20px;
    }
    .brand-title {
      font-size: 16px;
      font-weight: 700;
      letter-spacing: -0.3px;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand-sub {
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
      color: #4ade80;
      border-color: rgba(34, 197, 94, 0.3);
      background: rgba(34, 197, 94, 0.08);
    }
    .tag.model {
      color: var(--accent);
      border-color: rgba(56, 189, 248, 0.3);
      background: rgba(56, 189, 248, 0.08);
    }

    /* Active Run Progress Bar */
    .progress-bar-container {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px 14px;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .progress-bar-outer {
      flex: 1;
      height: 6px;
      background: #1e293b;
      border-radius: 3px;
      overflow: hidden;
    }
    .progress-bar-inner {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #38bdf8, #818cf8);
      border-radius: 3px;
      transition: width 0.4s ease;
    }
    .progress-info {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 12px;
      white-space: nowrap;
    }
    .progress-info .agent-badge {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 600;
      color: var(--accent);
      background: rgba(56, 189, 248, 0.12);
      padding: 2px 7px;
      border-radius: 3px;
      border: 1px solid rgba(56, 189, 248, 0.25);
    }

    /* Pipeline 8-Node Grid */
    .section-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--text-secondary);
      margin-bottom: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .pipeline-grid {
      display: grid;
      grid-template-columns: repeat(8, 1fr);
      gap: 8px;
      margin-bottom: 20px;
    }
    .node-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px 10px;
      position: relative;
      transition: all 0.25s ease;
      min-height: 84px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .node-card .node-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 4px;
    }
    .node-card .role-title {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.3px;
      color: var(--text-primary);
    }
    .node-card .model-pill {
      font-family: var(--font-mono);
      font-size: 9px;
      padding: 1px 4px;
      border-radius: 3px;
      background: rgba(255,255,255,0.06);
      color: var(--text-muted);
    }
    .node-card .node-status {
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.4px;
      color: var(--text-muted);
      margin-top: 2px;
    }
    .node-card .node-detail {
      font-size: 10px;
      color: var(--text-secondary);
      line-height: 1.3;
      margin-top: 4px;
      overflow: hidden;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }

    /* Node States & Animated Pulses */
    @keyframes pulse-working {
      0% {
        border-color: #38bdf8;
        box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.4);
      }
      50% {
        border-color: #818cf8;
        box-shadow: 0 0 0 5px rgba(56, 189, 248, 0);
      }
      100% {
        border-color: #38bdf8;
        box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.4);
      }
    }
    .node-card.running {
      animation: pulse-working 1.6s infinite ease-in-out;
      background: rgba(56, 189, 248, 0.05);
    }
    .node-card.running .node-status {
      color: var(--accent);
    }
    .node-card.done {
      border-color: rgba(34, 197, 94, 0.4);
      background: rgba(34, 197, 94, 0.04);
    }
    .node-card.done .node-status {
      color: var(--success);
    }
    .node-card.failed {
      border-color: rgba(239, 68, 68, 0.4);
      background: rgba(239, 68, 68, 0.04);
    }
    .node-card.failed .node-status {
      color: var(--error);
    }

    /* Main Content Layout */
    .main-grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 20px;
      align-items: start;
    }

    /* Left Control Panel */
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
    }
    .panel-header {
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
      background: var(--surface-card);
      font-size: 12px;
      font-weight: 600;
      color: var(--text-primary);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .panel-body {
      padding: 16px;
    }
    .field-group {
      margin-bottom: 14px;
    }
    .field-label {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-secondary);
      margin-bottom: 6px;
      display: block;
    }
    select, textarea, input {
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--text-primary);
      font-family: var(--font-sans);
      font-size: 12px;
      padding: 8px 10px;
      outline: none;
      transition: border-color 0.15s ease;
    }
    select:focus, textarea:focus, input:focus {
      border-color: var(--accent);
    }
    textarea {
      font-family: var(--font-mono);
      font-size: 12px;
      resize: vertical;
      min-height: 120px;
      line-height: 1.4;
    }
    .btn {
      width: 100%;
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
      padding: 10px 14px;
      cursor: pointer;
      transition: background 0.15s ease;
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 6px;
    }
    .btn:hover:not(:disabled) {
      background: #1d4ed8;
    }
    .btn:disabled {
      background: #1e293b;
      color: var(--text-muted);
      cursor: not-allowed;
    }
    .btn-secondary {
      background: var(--surface-card);
      border: 1px solid var(--border);
      color: var(--text-primary);
      margin-top: 8px;
    }
    .btn-secondary:hover:not(:disabled) {
      background: var(--surface-hover);
    }

    /* Run History List */
    .history-list {
      max-height: 160px;
      overflow-y: auto;
      margin-top: 14px;
      border: 1px solid var(--border);
      border-radius: 4px;
    }
    .history-item {
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-secondary);
      transition: background 0.15s ease;
    }
    .history-item:last-child {
      border-bottom: none;
    }
    .history-item:hover {
      background: var(--surface-hover);
      color: var(--text-primary);
    }
    .history-item.active {
      background: rgba(56, 189, 248, 0.1);
      color: var(--accent);
      border-left: 2px solid var(--accent);
    }

    /* Right Main Display Area */
    .right-column {
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    /* Live Activity Stream Terminal */
    .terminal-panel {
      background: #07090e;
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
    }
    .terminal-header {
      background: #0d121c;
      padding: 8px 14px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-secondary);
    }
    .terminal-indicator {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--text-muted);
    }
    .dot.live {
      background: #22c55e;
      box-shadow: 0 0 6px rgba(34, 197, 94, 0.6);
    }
    .terminal-body {
      height: 140px;
      overflow-y: auto;
      padding: 10px 14px;
      font-family: var(--font-mono);
      font-size: 11px;
      line-height: 1.6;
    }
    .log-line {
      display: flex;
      gap: 8px;
      margin-bottom: 2px;
      animation: fadeIn 0.2s ease-in;
    }
    .log-time {
      color: var(--text-muted);
    }
    .log-agent {
      color: var(--accent);
      font-weight: 600;
    }
    .log-msg {
      color: #cbd5e1;
    }

    /* Collateral Tabs */
    .tabs-header {
      display: flex;
      border-bottom: 1px solid var(--border);
      background: var(--surface-card);
      padding: 0 8px;
    }
    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-secondary);
      font-size: 12px;
      font-weight: 500;
      padding: 10px 14px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.15s ease;
    }
    .tab-btn:hover {
      color: var(--text-primary);
    }
    .tab-btn.active {
      color: var(--accent);
      border-bottom-color: var(--accent);
      font-weight: 600;
    }
    .tab-content {
      display: none;
      padding: 16px;
      animation: fadeIn 0.2s ease-out;
    }
    .tab-content.active {
      display: block;
    }

    /* Code View Area */
    .code-container {
      position: relative;
    }
    .code-toolbar {
      position: absolute;
      top: 8px;
      right: 8px;
      z-index: 10;
      display: flex;
      gap: 6px;
    }
    .tool-btn {
      background: var(--surface);
      border: 1px solid var(--border-bright);
      color: var(--text-secondary);
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .tool-btn:hover {
      background: var(--surface-hover);
      color: #fff;
    }
    pre {
      background: #07090e;
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 14px;
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.5;
      overflow-x: auto;
      max-height: 440px;
      color: #e2e8f0;
      white-space: pre-wrap;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(2px); }
      to { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-title">RTL-CODER ARCHITECTURE FRAMEWORK</div>
      <div class="brand-sub">Multi-Agent RTL Design, Verification & Automated EDA Suite</div>
    </div>
    <div class="system-status">
      <span class="tag online" id="wsl-badge">WSL2 EDA: ACTIVE</span>
      <span class="tag model" id="primary-model-badge">PRIMARY: qwen2.5-coder:3b</span>
      <span class="tag" id="fast-model-badge">FAST: qwen2.5-coder:1.5b</span>
      <span class="tag" id="ollama-badge">OLLAMA: READY</span>
    </div>
  </header>

  <!-- Live Progress & Spotlight Bar -->
  <div class="progress-bar-container">
    <div class="progress-info">
      <span class="agent-badge" id="spotlight-agent">STANDBY</span>
      <span id="spotlight-desc" style="color: var(--text-secondary);">Ready for hardware specification input.</span>
    </div>
    <div class="progress-bar-outer">
      <div class="progress-bar-inner" id="progress-bar"></div>
    </div>
    <div class="progress-info" style="font-family: var(--font-mono);" id="progress-percent">0%</div>
  </div>

  <!-- 8 Pipeline Agent Cards -->
  <div class="section-label">
    <span>Agent Execution Sequence</span>
    <span id="run-state-badge" style="font-family: var(--font-mono); font-weight: normal; color: var(--text-muted);">PIPELINE: IDLE</span>
  </div>

  <div class="pipeline-grid">
    <div class="node-card" id="card-SPEC_ANALYSIS">
      <div class="node-header">
        <span class="role-title">Spec Analyst</span>
        <span class="model-pill">1.5B</span>
      </div>
      <div class="node-status" id="status-SPEC_ANALYSIS">STANDBY</div>
      <div class="node-detail" id="detail-SPEC_ANALYSIS">Requirements synthesis & interface extraction</div>
    </div>

    <div class="node-card" id="card-ARCHITECTURE_DESIGN">
      <div class="node-header">
        <span class="role-title">Architect</span>
        <span class="model-pill">1.5B</span>
      </div>
      <div class="node-status" id="status-ARCHITECTURE_DESIGN">STANDBY</div>
      <div class="node-detail" id="detail-ARCHITECTURE_DESIGN">FSM state encoding & datapath partitioning</div>
    </div>

    <div class="node-card" id="card-RTL_GENERATION">
      <div class="node-header">
        <span class="role-title">RTL Coder</span>
        <span class="model-pill">3B</span>
      </div>
      <div class="node-status" id="status-RTL_GENERATION">STANDBY</div>
      <div class="node-detail" id="detail-RTL_GENERATION">Synthesizable Verilog RTL module coding</div>
    </div>

    <div class="node-card" id="card-VERIFICATION_GENERATION">
      <div class="node-header">
        <span class="role-title">Verif Engineer</span>
        <span class="model-pill">3B</span>
      </div>
      <div class="node-status" id="status-VERIFICATION_GENERATION">STANDBY</div>
      <div class="node-detail" id="detail-VERIFICATION_GENERATION">Self-checking testbench with safety watchdog</div>
    </div>

    <div class="node-card" id="card-SCRIPT_ENGINEER">
      <div class="node-header">
        <span class="role-title">Script Engineer</span>
        <span class="model-pill">1.5B</span>
      </div>
      <div class="node-status" id="status-SCRIPT_ENGINEER">STANDBY</div>
      <div class="node-detail" id="detail-SCRIPT_ENGINEER">Yosys synthesis script & Makefile automation</div>
    </div>

    <div class="node-card" id="card-EDA_EXECUTION">
      <div class="node-header">
        <span class="role-title">EDA Engine</span>
        <span class="model-pill">WSL2</span>
      </div>
      <div class="node-status" id="status-EDA_EXECUTION">STANDBY</div>
      <div class="node-detail" id="detail-EDA_EXECUTION">Icarus compile/sim, Verilator lint, Yosys synth</div>
    </div>

    <div class="node-card" id="card-REVIEW">
      <div class="node-header">
        <span class="role-title">Reviewer</span>
        <span class="model-pill">1.5B</span>
      </div>
      <div class="node-status" id="status-REVIEW">STANDBY</div>
      <div class="node-detail" id="detail-REVIEW">Simulation metrics audit & PASS/REPAIR judgment</div>
    </div>

    <div class="node-card" id="card-REFLECTION">
      <div class="node-header">
        <span class="role-title">Reflection</span>
        <span class="model-pill">1.5B</span>
      </div>
      <div class="node-status" id="status-REFLECTION">STANDBY</div>
      <div class="node-detail" id="detail-REFLECTION">Root-cause diagnosis & targeted self-repair loop</div>
    </div>
  </div>

  <!-- Main Grid: Controls Left, Live Output Right -->
  <div class="main-grid">

    <!-- Controls Column -->
    <div class="left-column">
      <div class="panel">
        <div class="panel-header">
          <span>Design Input & Control</span>
        </div>
        <div class="panel-body">
          <div class="field-group">
            <label class="field-label" for="preset-select">Architecture Presets</label>
            <select id="preset-select" onchange="loadPreset()">
              <option value="">Select a hardware design template...</option>
              <option value="counter" selected>4-bit Counter (Enable & Synchronous Reset)</option>
              <option value="fifo">Synchronous FIFO (8-bit, 16 words depth)</option>
              <option value="alu">8-bit ALU (8 operations + status flags)</option>
              <option value="uart_tx">UART Transmitter (8-N-1 115200 baud)</option>
              <option value="spi_master">SPI Master (Mode 0, 8-bit)</option>
            </select>
          </div>

          <div class="field-group">
            <label class="field-label" for="spec-text">Natural Language Specification</label>
            <textarea id="spec-text" spellcheck="false" placeholder="Enter hardware specification..."></textarea>
          </div>

          <button class="btn" id="run-btn" onclick="startGeneration()">
            Execute Generation & Verification
          </button>
          <button class="btn btn-secondary" onclick="openWaveforms()">
            Launch GTKWave Waveforms
          </button>

          <div style="margin-top: 18px;">
            <span class="field-label">Past Executions</span>
            <div class="history-list" id="runs-history">
              <div style="padding: 10px; color: var(--text-muted); text-align: center;">Loading runs...</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Output Column -->
    <div class="right-column">

      <!-- Live Activity Stream Console -->
      <div class="terminal-panel">
        <div class="terminal-header">
          <div class="terminal-indicator">
            <span class="dot live" id="terminal-dot"></span>
            <span>LIVE AGENT ACTIVITY FEED</span>
          </div>
          <span id="active-run-id">NO ACTIVE RUN</span>
        </div>
        <div class="terminal-body" id="terminal-body">
          <div class="log-line">
            <span class="log-time">[00:00:00]</span>
            <span class="log-agent">[System]</span>
            <span class="log-msg">Platform ready. Select a template or enter a specification to execute.</span>
          </div>
        </div>
      </div>

      <!-- Collateral Viewer Tabs -->
      <div class="panel">
        <div class="tabs-header">
          <button class="tab-btn active" onclick="switchTab('rtl')">Synthesized RTL (.v)</button>
          <button class="tab-btn" onclick="switchTab('testbench')">Verification Testbench (.v)</button>
          <button class="tab-btn" onclick="switchTab('eda')">EDA Tool Reports</button>
          <button class="tab-btn" onclick="switchTab('microarch')">Microarchitecture Plan</button>
          <button class="tab-btn" onclick="switchTab('requirements')">Requirements JSON</button>
          <button class="tab-btn" onclick="switchTab('review')">Quality Review Matrix</button>
        </div>

        <div class="tab-content active" id="tab-rtl">
          <div class="code-container">
            <div class="code-toolbar">
              <button class="tool-btn" onclick="copyCode('code-rtl')">Copy Verilog</button>
            </div>
            <pre id="code-rtl">// Verilog RTL module will be displayed here as RTL Coder generates it.</pre>
          </div>
        </div>

        <div class="tab-content" id="tab-testbench">
          <div class="code-container">
            <div class="code-toolbar">
              <button class="tool-btn" onclick="copyCode('code-tb')">Copy Testbench</button>
            </div>
            <pre id="code-tb">// Self-checking testbench will appear here when Verification Engineer completes.</pre>
          </div>
        </div>

        <div class="tab-content" id="tab-eda">
          <div class="code-container">
            <pre id="code-eda">// EDA execution reports (Icarus simulation, Verilator lint, Yosys synthesis stats) will stream here.</pre>
          </div>
        </div>

        <div class="tab-content" id="tab-microarch">
          <div class="code-container">
            <pre id="code-arch">// Microarchitectural JSON specification formulated by Architect Agent.</pre>
          </div>
        </div>

        <div class="tab-content" id="tab-requirements">
          <div class="code-container">
            <pre id="code-reqs">// Extracted ports, clock domains, and control parameters from Specification Analyst.</pre>
          </div>
        </div>

        <div class="tab-content" id="tab-review">
          <div class="code-container">
            <pre id="code-review">// Reviewer analysis report and verification verdict.</pre>
          </div>
        </div>
      </div>

    </div>

  </div>

  <script>
    const PRESETS = {
      counter: "Module Name: counter\\nDescription: 4-bit synchronous up-counter with synchronous active-low reset and enable.\\nPort Specifications:\\n- clk: 1-bit input clock\\n- rst_n: 1-bit input synchronous active-low reset\\n- en: 1-bit input enable signal\\n- count: 4-bit output count value",
      fifo: "Module Name: fifo_sync\\nDescription: 8-bit synchronous FIFO with 16 words depth.\\nPort Specifications:\\n- clk: 1-bit input clock\\n- rst_n: 1-bit input synchronous active-low reset\\n- wr_en: 1-bit input write enable\\n- rd_en: 1-bit input read enable\\n- wr_data: 8-bit input data to write\\n- rd_data: 8-bit output data read from FIFO\\n- full: 1-bit output status flag\\n- empty: 1-bit output status flag",
      alu: "Module Name: alu\\nDescription: 8-bit Arithmetic Logic Unit with operations ADD, SUB, AND, OR, XOR, SHL, SHR, PASS_A and flags zero, carry, negative.",
      uart_tx: "Module Name: uart_tx\\nDescription: UART Transmitter 8-N-1 format transmitting 8 data bits with start and stop bits.",
      spi_master: "Module Name: spi_master\\nDescription: SPI Master Mode 0 controller supporting 8-bit full-duplex transfers."
    };

    let activeRunId = null;
    let pollInterval = null;
    let currentArtifacts = {};

    function loadPreset() {
      const val = document.getElementById('preset-select').value;
      if (PRESETS[val]) {
        document.getElementById('spec-text').value = PRESETS[val].replace(/\\\\n/g, '\\n');
      }
    }

    function switchTab(name) {
      const tabs = ['rtl', 'testbench', 'eda', 'microarch', 'requirements', 'review'];
      tabs.forEach(t => {
        const btn = document.querySelector(`[onclick="switchTab('${t}')"]`);
        const content = document.getElementById(`tab-${t}`);
        if (btn) btn.classList.toggle('active', t === name);
        if (content) content.classList.toggle('active', t === name);
      });
    }

    function copyCode(id) {
      const text = document.getElementById(id).innerText;
      navigator.clipboard.writeText(text);
      alert('Copied to clipboard');
    }

    async function initSystem() {
      loadPreset();
      await fetchRuns();
    }

    async function fetchRuns() {
      try {
        const res = await fetch('/api/runs');
        const runs = await res.json();
        const container = document.getElementById('runs-history');
        if (!runs || runs.length === 0) {
          container.innerHTML = '<div style="padding: 10px; color: var(--text-muted); text-align: center;">No prior runs</div>';
          return;
        }

        container.innerHTML = runs.map(r => `
          <div class="history-item ${r.run_id === activeRunId ? 'active' : ''}" onclick="selectRun('${r.run_id}')">
            <span>${r.run_id}</span>
            <span style="color: ${r.status === 'PASS' ? 'var(--success)' : (r.status === 'RUNNING' ? 'var(--accent)' : 'var(--text-muted)')}; font-weight: 600;">
              ${r.status}
            </span>
          </div>
        `).join('');
      } catch (e) {
        console.error('Failed to fetch runs:', e);
      }
    }

    function selectRun(runId) {
      activeRunId = runId;
      document.getElementById('active-run-id').innerText = runId;
      if (pollInterval) clearInterval(pollInterval);
      pollLiveStatus(runId);
      // If it is running, poll continuously
      pollInterval = setInterval(() => pollLiveStatus(runId), 800);
    }

    async function startGeneration() {
      const spec = document.getElementById('spec-text').value.trim();
      if (!spec) return alert('Enter a specification or select a preset.');

      const btn = document.getElementById('run-btn');
      btn.disabled = true;
      btn.innerText = 'Initializing Agents...';

      // Reset UI pipeline state
      resetPipelineVisuals();

      try {
        const res = await fetch('/api/runs', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({spec_text: spec})
        });
        const result = await res.json();
        if (result.run_id) {
          activeRunId = result.run_id;
          document.getElementById('active-run-id').innerText = result.run_id;
          await fetchRuns();

          // Start rapid polling
          if (pollInterval) clearInterval(pollInterval);
          pollInterval = setInterval(() => pollLiveStatus(result.run_id), 600);
        }
      } catch(e) {
        alert('Pipeline execution error: ' + e);
        btn.disabled = false;
        btn.innerText = 'Execute Generation & Verification';
      }
    }

    function resetPipelineVisuals() {
      const stages = ['SPEC_ANALYSIS', 'ARCHITECTURE_DESIGN', 'RTL_GENERATION', 'VERIFICATION_GENERATION', 'SCRIPT_ENGINEER', 'EDA_EXECUTION', 'REVIEW', 'REFLECTION'];
      stages.forEach(s => {
        const card = document.getElementById(`card-${s}`);
        const status = document.getElementById(`status-${s}`);
        if (card) {
          card.className = 'node-card';
        }
        if (status) {
          status.innerText = 'STANDBY';
        }
      });
      document.getElementById('progress-bar').style.width = '5%';
      document.getElementById('progress-percent').innerText = '5%';
      document.getElementById('terminal-body').innerHTML = '';
      document.getElementById('run-state-badge').innerText = 'PIPELINE: STARTING';
    }

    async function pollLiveStatus(runId) {
      try {
        const res = await fetch(`/api/runs/${runId}/live`);
        if (!res.ok) return;
        const data = await res.json();

        // 1. Update Progress Bar & Spotlight
        const pct = data.progress_percent || 10;
        document.getElementById('progress-bar').style.width = `${pct}%`;
        document.getElementById('progress-percent').innerText = `${pct}%`;
        document.getElementById('spotlight-agent').innerText = data.active_agent || 'PIPELINE';
        document.getElementById('spotlight-desc').innerText = data.agent_role_desc || 'In progress...';
        document.getElementById('run-state-badge').innerText = `PIPELINE: ${data.status || 'RUNNING'}`;

        // 2. Update Stage Cards
        if (data.stages) {
          Object.keys(data.stages).forEach(s => {
            const stage = data.stages[s];
            const card = document.getElementById(`card-${s}`);
            const statusEl = document.getElementById(`status-${s}`);
            const detailEl = document.getElementById(`detail-${s}`);

            if (card && stage) {
              card.className = 'node-card';
              if (stage.status === 'RUNNING') {
                card.classList.add('running');
                statusEl.innerText = 'WORKING';
              } else if (stage.status === 'DONE') {
                card.classList.add('done');
                statusEl.innerText = 'COMPLETE';
              } else if (stage.status === 'FAILED') {
                card.classList.add('failed');
                statusEl.innerText = 'REPAIR';
              } else {
                statusEl.innerText = 'STANDBY';
              }

              if (stage.detail && detailEl) {
                detailEl.innerText = stage.detail;
              }
            }
          });
        }

        // 3. Update Activity Feed Terminal
        if (data.logs && Array.isArray(data.logs)) {
          const body = document.getElementById('terminal-body');
          body.innerHTML = data.logs.map(l => `
            <div class="log-line">
              <span class="log-time">[${l.time}]</span>
              <span class="log-agent">[${l.agent}]</span>
              <span class="log-msg">${escapeHtml(l.message)}</span>
            </div>
          `).join('');
          body.scrollTop = body.scrollHeight;
        }

        // 4. Update Collateral Tabs
        if (data.artifacts) {
          const art = data.artifacts;
          if (art.rtl && art.rtl !== currentArtifacts.rtl) {
            document.getElementById('code-rtl').innerText = art.rtl;
            currentArtifacts.rtl = art.rtl;
          }
          if (art.testbench && art.testbench !== currentArtifacts.testbench) {
            document.getElementById('code-tb').innerText = art.testbench;
            currentArtifacts.testbench = art.testbench;
          }
          if (art.eda_reports && art.eda_reports !== currentArtifacts.eda_reports) {
            document.getElementById('code-eda').innerText = art.eda_reports;
            currentArtifacts.eda_reports = art.eda_reports;
          }
          if (art.architecture) {
            document.getElementById('code-arch').innerText = JSON.stringify(art.architecture, null, 2);
          }
          if (art.requirements) {
            document.getElementById('code-reqs').innerText = JSON.stringify(art.requirements, null, 2);
          }
          if (art.review) {
            document.getElementById('code-review').innerText = JSON.stringify(art.review, null, 2);
          }
        }

        // 5. Completion check
        const isTerminal = (data.status === 'SUCCESS' || data.status === 'HUMAN_ESCALATION' || data.status === 'FAILED');
        if (isTerminal) {
          clearInterval(pollInterval);
          pollInterval = null;
          const btn = document.getElementById('run-btn');
          btn.disabled = false;
          btn.innerText = 'Execute Generation & Verification';
          await fetchRuns();
        }
      } catch (e) {
        console.error('Live poll error:', e);
      }
    }

    function escapeHtml(str) {
      if (!str) return '';
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    async function openWaveforms() {
      if (!activeRunId) return alert('Select or run an execution first.');
      try {
        const res = await fetch(`/api/runs/${activeRunId}/wave`, {method: 'POST'});
        const data = await res.json();
        if (data.status === 'launched') {
          alert('GTKWave waveform viewer launched in WSL2.');
        } else {
          alert('No .vcd waveform file found for this execution yet.');
        }
      } catch(e) {
        alert('Unable to launch GTKWave viewer: ' + e);
      }
    }

    initSystem();
  </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serves the main interactive dashboard interface."""
    return HTMLResponse(content=DASHBOARD_HTML)


@router.get("/api/system/status")
def system_status() -> Dict[str, Any]:
    """Audits local LLM and WSL EDA availability."""
    ollama = OllamaClient()
    ok, models = ollama.check_health()
    return {
        "ollama_online": ok,
        "primary_model": config.primary_model,
        "fast_model": config.fast_model,
        "installed_models": models,
        "wsl_ready": True,
    }


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
            elif (d / "live_status.json").exists():
                try:
                    live_data = json.loads((d / "live_status.json").read_text(encoding="utf-8"))
                    status = live_data.get("status", "RUNNING")
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


@router.get("/api/runs/{run_id}/live")
def get_run_live(run_id: str) -> Dict[str, Any]:
    """Retrieves real-time status and live generated collateral for visualization."""
    run_dir = config.base_dir / "runs" / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    status_file = run_dir / "live_status.json"
    if status_file.exists():
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            artifacts = data.setdefault("artifacts", {})
            if not artifacts.get("rtl"):
                rtl_files = list((run_dir / "rtl").glob("*.v")) if (run_dir / "rtl").exists() else []
                if rtl_files:
                    artifacts["rtl"] = rtl_files[0].read_text(encoding="utf-8")
            if not artifacts.get("testbench"):
                tb_files = list((run_dir / "verification").glob("*.v")) if (run_dir / "verification").exists() else []
                if tb_files:
                    artifacts["testbench"] = tb_files[0].read_text(encoding="utf-8")
            if not artifacts.get("requirements"):
                req_file = run_dir / "requirements.json"
                if req_file.exists():
                    artifacts["requirements"] = json.loads(req_file.read_text(encoding="utf-8"))
            if not artifacts.get("architecture"):
                arch_file = run_dir / "architecture.json"
                if arch_file.exists():
                    artifacts["architecture"] = json.loads(arch_file.read_text(encoding="utf-8"))
            if not artifacts.get("review"):
                rev_files = list((run_dir / "reports").glob("review_iter_*.json")) if (run_dir / "reports").exists() else []
                if rev_files:
                    artifacts["review"] = json.loads(sorted(rev_files)[-1].read_text(encoding="utf-8"))
            if not artifacts.get("eda_reports"):
                if (run_dir / "reports").exists():
                    logs = []
                    for lf in sorted((run_dir / "reports").glob("*.log")):
                        logs.append(f"=== {lf.name} ===\n" + lf.read_text(encoding="utf-8", errors="replace"))
                    if logs:
                        artifacts["eda_reports"] = "\n\n".join(logs)
            return data
        except Exception:
            pass

    # Fallback to get_run
    run_data = get_run(run_id)
    return {
        "run_id": run_id,
        "status": "COMPLETED",
        "current_state": "SUCCESS" if run_data.get("review", {}).get("status") == "PASS" else "COMPLETED",
        "active_agent": "None",
        "agent_role_desc": "Execution finished",
        "progress_percent": 100,
        "stages": {},
        "logs": [],
        "artifacts": {
            "rtl": run_data.get("rtl"),
            "testbench": run_data.get("testbench"),
            "requirements": run_data.get("requirements"),
            "architecture": run_data.get("architecture"),
            "review": run_data.get("review"),
            "eda_reports": run_data.get("eda_reports"),
        }
    }


class RunRequest(BaseModel):
    spec_text: str


def _run_pipeline_worker(run_id: str, spec_text: str):
    """Executes the closed-loop pipeline asynchronously in a background thread."""
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

    try:
        run_paths = create_run_layout(run_id=run_id, base_dir=config.base_dir / "runs")
        ctx = PipelineContext(
            run_id=run_id,
            run_paths=run_paths,
            spec_text=spec_text,
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

        orchestrator.run(ctx)
    except Exception as ex:
        status_file = config.base_dir / "runs" / run_id / "live_status.json"
        try:
            status_data = json.loads(status_file.read_text(encoding="utf-8")) if status_file.exists() else {}
        except Exception:
            status_data = {}
        status_data["status"] = "FAILED"
        logs = status_data.setdefault("logs", [])
        logs.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "agent": "System",
            "message": f"Execution error: {str(ex)}",
        })
        try:
            status_file.write_text(json.dumps(status_data, indent=2), encoding="utf-8")
        except Exception:
            pass


@router.post("/api/runs")
def trigger_run(payload: RunRequest) -> Dict[str, Any]:
    """Runs the multi-agent closed-loop flow asynchronously from the dashboard."""
    run_id = f"web_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Pre-create directory and initial live_status.json so immediate first poll succeeds
    run_dir = config.base_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    initial_status = {
        "run_id": run_id,
        "status": "RUNNING",
        "current_state": "SPEC_ANALYSIS",
        "active_agent": "Specification Analyst",
        "agent_role_desc": "Parsing requirements schema and extracting ports...",
        "iteration": 0,
        "progress_percent": 8,
        "stages": {
            "SPEC_ANALYSIS": {"name": "Spec Analyst", "status": "RUNNING", "detail": "Extracting ports & clocking with 1.5B", "badge": "1.5B"},
            "ARCHITECTURE_DESIGN": {"name": "Architect", "status": "WAITING", "detail": "Pending microarchitecture planning", "badge": "1.5B"},
            "RTL_GENERATION": {"name": "RTL Coder", "status": "WAITING", "detail": "Pending Verilog synthesis", "badge": "3B"},
            "VERIFICATION_GENERATION": {"name": "Verif Engineer", "status": "WAITING", "detail": "Pending testbench generation", "badge": "3B"},
            "SCRIPT_ENGINEER": {"name": "Script Engineer", "status": "WAITING", "detail": "Pending EDA script generation", "badge": "1.5B"},
            "EDA_EXECUTION": {"name": "EDA Engine", "status": "WAITING", "detail": "Pending WSL2 execution", "badge": "WSL2"},
            "REVIEW": {"name": "Reviewer", "status": "WAITING", "detail": "Pending verification review", "badge": "1.5B"},
            "REFLECTION": {"name": "Reflection", "status": "WAITING", "detail": "Pending diagnosis & repair", "badge": "1.5B"},
        },
        "logs": [
            {"time": datetime.now().strftime("%H:%M:%S"), "agent": "System", "message": f"Run '{run_id}' registered. Closed-loop multi-agent flow dispatched."}
        ],
        "artifacts": {
            "spec_text": payload.spec_text,
            "requirements": None,
            "architecture": None,
            "rtl": None,
            "testbench": None,
            "eda_reports": None,
            "review": None,
        }
    }
    (run_dir / "live_status.json").write_text(json.dumps(initial_status, indent=2), encoding="utf-8")

    worker_thread = threading.Thread(
        target=_run_pipeline_worker,
        args=(run_id, payload.spec_text),
        daemon=False,
    )
    worker_thread.start()

    return {"run_id": run_id, "status": "started"}


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
