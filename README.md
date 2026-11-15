# Multi-Agent AI Framework for Hardware – RTL Design, UVM Verification and EDA Flow

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Phase 1](https://img.shields.io/badge/Status-Phase%201%20Skeleton-green.svg)](#)

A locally deployed, privacy-preserving multi-agent AI framework for automated digital hardware design, verification, and EDA flow automation. Designed for final-year engineering project at **SDM College of Engineering & Technology, Dharwad**.

---

## 1. System Architecture

```text
┌────────────────────────────────────────────────────────┐
│               Hardware Specification / User            │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               Multi-Agent Orchestration                │
│                                                        │
│  Specification Analyst ──► Architect ──► RTL Coder     │
│                                │             │         │
│                                ▼             ▼         │
│                      Verification Engineer   │         │
│                                │             │         │
│                                ▼             ▼         │
│                         Script Engineer      │         │
│                                │             │         │
│                                ▼             ▼         │
│                         Reviewer ◄──► Reflection       │
└───────────────────────────┬────────────────────────────┘
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
┌─────────────────────────┐   ┌──────────────────────────┐
│  Inference Gateway      │   │  Knowledge / RAG         │
│  (FastAPI on localhost) │   │  (Embeddings / Chroma)   │
│  Open-weight Models     │   │  Specs / Datasheets / IP │
│  (Ollama: Qwen2.5-Coder)│   └──────────────────────────┘
└────────────┬────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────┐
│                     EDA Tool Layer                     │
│  Compilation (iverilog) │ Linting (verilator)          │
│  Simulation (vvp/cocotb)│ Synthesis (yosys)            │
│  Coverage (verilator)   │ Waveforms (gtkwave)          │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│          Shared Version-Controlled Repository          │
│  runs/<run_id>/{spec, reqs, arch, rtl, tb, reports}    │
└────────────────────────────────────────────────────────┘
```

---

## 2. Team Member Workload Split

| USN | Member Name | Role & Ownership | Primary Directory |
| :--- | :--- | :--- | :--- |
| **2SD23CS052** | **Mahant Arawal** | Orchestrator State Machine & Local Gateway | `orchestrator/`, `gateway/`, `schemas/` |
| **2SD23CS016** | **Anushree P Hemadri** | EDA Tool Wrappers & Script Engineering | `eda/`, `agents/script_engineer.py` |
| **2SD23CS081** | **Ruthvik Janamatti** | Spec Analyst, Architect & RTL Coder Agents | `agents/spec_analyst.py`, `agents/architect.py`, `agents/rtl_coder.py` |
| **2SD23CS090** | **Sanvi Rashinkar** | Verification, Reflection, Benchmarks & RAG | `agents/verification_engineer.py`, `agents/reviewer.py`, `agents/reflection.py`, `benchmarks/`, `rag/` |

---

## 3. Directory Layout

```text
RTL CODER/
├── agents/             # The 7 specialized AI agents
├── orchestrator/       # State machine, loop manager & human escalation
├── gateway/            # FastAPI local inference gateway (/generate endpoint)
├── eda/                # Python wrappers for iverilog, verilator, yosys, gtkwave
├── schemas/            # Pydantic schemas for structured inputs, outputs & run layout
├── designs/            # Benchmark reference designs (counter, FIFO, FSM, SPI/UART)
├── runs/               # Per-run artifact folders: runs/<run_id>/
├── benchmarks/         # VerilogEval and RTLLM benchmark execution harness
├── evaluation/         # Metrics collection, analysis & CSV/plot generators
├── rag/                # Local knowledge retrieval layer (vector store)
├── tests/              # Automated unit and integration test suite
├── docs/               # Architectural decisions (DECISIONS.md) & project documentation
├── pyproject.toml      # Build metadata and dependencies
└── requirements.txt    # Python requirements
```

---

## 4. Per-Run Artefact Layout

Each pipeline execution creates an isolated, versioned run folder:
```text
runs/<run_id>/
├── spec/               # Original natural-language specification
├── requirements.json   # Specification Analyst output
├── architecture.json   # Architect output (registers, state transitions, datapaths)
├── rtl/                # Synthesizable Verilog/SystemVerilog sources
├── verification/       # Testbenches (cocotb/pyuvm), SVA, test stimuli
├── scripts/            # Generated EDA execution scripts (Bash/TCL/Python)
├── reports/            # Simulation logs, lint reports, synthesis timing/area, coverage
└── history/            # Agent iteration diffs, review findings, and commit logs
```

---

## 5. Quick Start

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Verify Stack (Smoke Test)
```powershell
python -m pytest tests/test_smoke.py
```
