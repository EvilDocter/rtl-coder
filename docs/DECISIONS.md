# Architecture Decision Records (ADRs)

## ADR-001: Local CPU Inference Engine (Ollama + GGUF Quantization)
- **Status:** Approved
- **Context:** Chapter 8.1 of the synopsis mentions an NVIDIA GPU for local inference. However, the host system is powered by an AMD Ryzen 6-Core processor with integrated AMD Radeon graphics (no NVIDIA CUDA core support).
- **Decision:** Use **Ollama** as the local serving engine using AVX2 CPU acceleration. Deploy quantized models (`Qwen2.5-Coder:3b` as the primary workhorse, and `Qwen2.5-Coder:1.5b` for fast JSON transformations and reviews).
- **Trade-off:** Dropping 7B in favor of the lightweight 3B model (1.9 GB) yields ~3x faster inference times on AMD Ryzen CPU (8-14s vs 40s+ per turn) while leaving >11 GB free RAM for OS and EDA synthesis/simulation tools. The FastAPI gateway isolates all agent code from model serving details, allowing seamless connection to a college GPU server or external instance later if available.

## ADR-002: WSL2 (Ubuntu 24.04) as the EDA Tool Execution Host
- **Status:** Approved
- **Context:** `iverilog`, `verilator`, and `yosys` are required. While `iverilog` runs natively on Windows, `verilator` and `yosys` are notoriously brittle and non-standard on native Windows.
- **Decision:** Execute all EDA tool commands inside Ubuntu-24.04 on WSL2 using `wsl --exec <tool> <args>` wrappers from Python.
- **Consequence:** Provides 100% Linux-standard behavior, official Debian packages (`apt install verilator yosys`), and eliminates cross-compilation errors.

## ADR-003: Deterministic Per-Run Artefact Layout
- **Status:** Approved
- **Context:** The synopsis mandates reproducible traceability across the *generate -> verify -> analyse -> correct* cycle.
- **Decision:** Every run creates an isolated folder under `runs/<run_id>/` with dedicated subdirectories:
  - `spec/`: Raw specification text
  - `requirements.json`: Structured requirements from Specification Analyst
  - `architecture.json`: Micro-architecture specification from Architect
  - `rtl/`: Generated synthesizable Verilog/SystemVerilog
  - `verification/`: cocotb/pyuvm testbenches, stimuli, assertions
  - `scripts/`: EDA automation scripts
  - `reports/`: Raw and parsed EDA reports (lint, sim, synth, coverage)
  - `history/`: Agent iteration records, diffs, and git commit hashes

## ADR-004: Explicit State-Machine Orchestrator with Human Escalation
- **Status:** Approved
- **Context:** Closed-loop agent feedback must not enter infinite repair loops.
- **Decision:** Implement a deterministic finite state machine with configurable `max_iterations` (default: 5). If verification criteria remain unsatisfied after `max_iterations`, the system transitions to an explicit `HUMAN_ESCALATION` state requesting manual guidance.
