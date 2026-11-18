"""Unified Command-Line Interface for the Multi-Agent Hardware Framework."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents import (
    ArchitectAgent,
    ReflectionAgent,
    ReviewerAgent,
    RTLCoderAgent,
    ScriptEngineerAgent,
    SpecificationAnalystAgent,
    VerificationEngineerAgent,
)
from eda.runner import WSLCommandRunner
from gateway.client import OllamaClient
from gateway.config import config
from gateway.gateway_client import InferenceGatewayClient
from orchestrator import Orchestrator, PipelineContext, PipelineState, RealEDAExecutor
from schemas import create_run_layout


def format_header(title: str) -> str:
    line = "=" * 70
    return f"\n{line}\n  {title}\n{line}"


def cmd_status(args: argparse.Namespace):
    """Audits local LLM models and WSL EDA tools."""
    print(format_header("ENVIRONMENT & TOOLCHAIN AUDIT"))

    # 1. Ollama Health
    ollama = OllamaClient()
    ok, models = ollama.check_health()
    if ok:
        print("[Ollama] Daemon Status: ONLINE (http://127.0.0.1:11434)")
        print(f"[Ollama] Installed Models ({len(models)}):")
        for m in models:
            is_pri = " (PRIMARY WORKHORSE)" if config.primary_model in m else ""
            is_fst = " (FAST MODEL)" if config.fast_model in m else ""
            print(f"  * {m}{is_pri}{is_fst}")
    else:
        print("[Ollama] Daemon Status: OFFLINE or UNREACHABLE")

    # 2. WSL & EDA Suite
    runner = WSLCommandRunner()
    print(f"\n[WSL] Engine: {runner.wsl_bin}")
    tools = ["iverilog", "verilator", "yosys", "gtkwave"]
    for t in tools:
        code, out, _, _ = runner.run_command(["which", t])
        if code == 0:
            version_cmd = [t, "-V"] if t in ("iverilog", "yosys") else [t, "--version"]
            _, v_out, _, _ = runner.run_command(version_cmd)
            v_line = v_out.splitlines()[0] if v_out.splitlines() else "installed"
            print(f"  * {t:10s} : INSTALLED ({v_line[:50]})")
        else:
            print(f"  * {t:10s} : NOT FOUND in WSL")

    print(format_header("AUDIT COMPLETE"))


def cmd_list_runs(args: argparse.Namespace):
    """Lists past execution runs in the workspace."""
    print(format_header("PAST HARDWARE GENERATION RUNS"))
    runs_dir = config.base_dir / "runs"
    if not runs_dir.exists():
        print("No runs found in ./runs")
        return

    runs = [d for d in runs_dir.iterdir() if d.is_dir() and d.name != "history"]
    if not runs:
        print("No runs found in ./runs")
        return

    print(f"{'RUN ID':<25} {'DATE/TIME':<20} {'FILES':<10}")
    print("-" * 60)
    for r in sorted(runs, key=lambda x: x.stat().st_mtime, reverse=True):
        mtime = datetime.fromtimestamp(r.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        file_count = sum(1 for _ in r.rglob("*") if _.is_file())
        print(f"{r.name:<25} {mtime:<20} {file_count:<10}")


def cmd_inspect(args: argparse.Namespace):
    """Displays collateral, logs, and triggers waveform display for a run."""
    run_dir = config.base_dir / "runs" / args.run_id
    if not run_dir.exists():
        print(f"Run ID '{args.run_id}' not found in {run_dir}")
        return

    print(format_header(f"RUN INSPECTOR: {args.run_id}"))

    rtl_files = list((run_dir / "rtl").glob("*.v")) if (run_dir / "rtl").exists() else []
    if rtl_files:
        print(f"\n[Generated RTL: {rtl_files[0].name}]")
        print("-" * 50)
        print(rtl_files[0].read_text(encoding="utf-8"))

    tb_files = list((run_dir / "verification").glob("*.v")) if (run_dir / "verification").exists() else []
    if tb_files:
        print(f"\n[Generated Testbench: {tb_files[0].name}]")
        print("-" * 50)
        print(tb_files[0].read_text(encoding="utf-8"))

    reports = list((run_dir / "reports").glob("review_iter_*.json")) if (run_dir / "reports").exists() else []
    if reports:
        last_rep = sorted(reports)[-1]
        print(f"\n[Final Review: {last_rep.name}]")
        print("-" * 50)
        print(last_rep.read_text(encoding="utf-8"))

    # Waveform Viewer Trigger
    vcd_files = list((run_dir / "reports").glob("*.vcd")) + list((run_dir / "verification").glob("*.vcd"))
    if args.wave and vcd_files:
        vcd_path = vcd_files[0]
        print(f"\nLaunching GTKWave for {vcd_path}...")
        runner = WSLCommandRunner()
        wsl_vcd = runner.to_wsl_path(vcd_path)
        subprocess.Popen(["wsl", "--exec", "gtkwave", wsl_vcd])
    elif args.wave:
        print("\nNo .vcd waveform file found in this run.")


def cmd_run(args: argparse.Namespace):
    """Runs the full autonomous multi-agent hardware flow."""
    spec_text = ""
    if args.spec:
        spec_text = args.spec
    elif args.file:
        spec_path = Path(args.file)
        if not spec_path.exists():
            print(f"Error: Spec file not found: {spec_path}")
            sys.exit(1)
        spec_text = spec_path.read_text(encoding="utf-8")
    elif args.preset:
        preset_file = config.base_dir / "designs" / args.preset / "spec.txt"
        if not preset_file.exists():
            print(f"Error: Preset '{args.preset}' not found in designs/")
            sys.exit(1)
        spec_text = preset_file.read_text(encoding="utf-8")
    else:
        print("Error: Must provide --spec <text>, --file <path>, or --preset <name>")
        sys.exit(1)

    run_id = args.run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(format_header(f"MULTI-AGENT HARDWARE GENERATION: {run_id}"))
    print(f"Target Specification:\n\"\"\"\n{spec_text.strip()}\n\"\"\"\n")

    run_paths = create_run_layout(run_id=run_id, base_dir=config.base_dir / "runs")
    ctx = PipelineContext(
        run_id=run_id,
        run_paths=run_paths,
        spec_text=spec_text,
        max_iterations=args.max_iterations,
    )

    client = InferenceGatewayClient()
    fast_model = config.fast_model
    primary_model = config.primary_model

    print(f"[Agents] Initializing 7 agents with models: Primary={primary_model}, Fast={fast_model}")
    spec_agent = SpecificationAnalystAgent(gateway_client=client, model=fast_model, temperature=0.0)
    arch_agent = ArchitectAgent(gateway_client=client, model=fast_model, temperature=0.0)
    rtl_agent = RTLCoderAgent(gateway_client=client, model=primary_model, temperature=0.0)
    verif_agent = VerificationEngineerAgent(gateway_client=client, model=primary_model, temperature=0.0)
    script_agent = ScriptEngineerAgent(gateway_client=client, model=fast_model, temperature=0.0)
    eda_executor = RealEDAExecutor()
    reviewer_agent = ReviewerAgent(gateway_client=client, model=fast_model)
    reflection_agent = ReflectionAgent(gateway_client=client, model=fast_model)

    orchestrator = Orchestrator(
        spec_agent=spec_agent,
        arch_agent=arch_agent,
        rtl_agent=rtl_agent,
        verif_agent=verif_agent,
        script_agent=script_agent,
        eda_executor=eda_executor,
        reviewer_agent=reviewer_agent,
        reflection_agent=reflection_agent,
        enable_git_commits=args.git,
    )

    start_time = time.time()
    final_state = orchestrator.run(ctx)
    elapsed = time.time() - start_time

    print(format_header("EXECUTION SUMMARY"))
    print(f"Final State  : {final_state.value}")
    print(f"Total Time   : {elapsed:.2f}s")
    print(f"Iterations   : {ctx.iteration}")
    if ctx.review:
        print(f"Review Ruling: {ctx.review.status}")
        print(f"Lint Clean   : {ctx.review.lint_clean}")
        print(f"Sim Clean    : {ctx.review.simulation_clean}")
        print(f"Synth Clean  : {ctx.review.synthesis_clean}")

    print(f"\nGenerated Artefacts in: {run_paths.run_dir}")
    if ctx.rtl and ctx.rtl.file_path:
        print(f"  * RTL Code    : {ctx.rtl.file_path}")
    if ctx.verification and ctx.verification.file_path:
        print(f"  * Testbench   : {ctx.verification.file_path}")
    if ctx.eda_scripts:
        for s in ctx.eda_scripts:
            print(f"  * EDA Script  : {s.file_path}")


def cmd_serve(args: argparse.Namespace):
    """Starts the FastAPI inference gateway and interactive Web Dashboard."""
    import uvicorn
    from gateway.service import app

    print(format_header("STARTING FASTAPI GATEWAY & DASHBOARD"))
    print(f"Dashboard URL: http://{args.host}:{args.port}")
    print(f"API Docs     : http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port)


def main():
    parser = argparse.ArgumentParser(
        prog="rtl-coder",
        description="Multi-Agent AI Framework for Hardware - RTL Design, Verification & EDA Flow",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Check local Ollama and WSL EDA tools")
    p_status.set_defaults(func=cmd_status)

    # run
    p_run = subparsers.add_parser("run", help="Run the multi-agent closed-loop hardware flow")
    p_run.add_argument("--spec", type=str, help="Specification description in natural language")
    p_run.add_argument("--file", type=str, help="Path to specification text file")
    p_run.add_argument("--preset", type=str, help="Preset module name from designs/ (e.g. counter, fsm, fifo, alu, uart_tx)")
    p_run.add_argument("--run-id", type=str, help="Custom identifier for this run")
    p_run.add_argument("--max-iterations", type=int, default=5, help="Max self-repair iterations")
    p_run.add_argument("--git", action="store_true", help="Enable git commits per pipeline state")
    p_run.set_defaults(func=cmd_run)

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect generated collateral and reports from a run")
    p_inspect.add_argument("run_id", type=str, help="Run identifier to inspect")
    p_inspect.add_argument("--wave", action="store_true", help="Launch GTKWave for simulation waveforms")
    p_inspect.set_defaults(func=cmd_inspect)

    # list-runs
    p_list = subparsers.add_parser("list-runs", help="List all past hardware generation runs")
    p_list.set_defaults(func=cmd_list_runs)

    # serve
    p_serve = subparsers.add_parser("serve", help="Start FastAPI gateway and Web Dashboard")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host interface")
    p_serve.add_argument("--port", type=int, default=8000, help="Port")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
