"""Smoke test suite to verify repo setup, environment, schemas, and tool execution."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from schemas.run_layout import create_run_layout, RunPaths


def test_python_version():
    """Verify runtime Python is >= 3.11."""
    assert sys.version_info >= (3, 11), f"Python 3.11+ required, got {sys.version}"


def test_core_package_imports():
    """Verify all monorepo module placeholders import cleanly."""
    import agents
    import benchmarks
    import eda
    import evaluation
    import gateway
    import orchestrator
    import rag
    import schemas

    assert all([agents, benchmarks, eda, evaluation, gateway, orchestrator, rag, schemas])


def test_run_layout_creation(tmp_path: Path):
    """Verify that create_run_layout builds the exact mandated per-run folder structure."""
    run_paths = create_run_layout(run_id="test_run_001", base_dir=tmp_path)

    assert isinstance(run_paths, RunPaths)
    assert run_paths.run_dir.exists()
    assert run_paths.spec_dir.is_dir()
    assert run_paths.rtl_dir.is_dir()
    assert run_paths.verification_dir.is_dir()
    assert run_paths.scripts_dir.is_dir()
    assert run_paths.reports_dir.is_dir()
    assert run_paths.history_dir.is_dir()

    # Check path conversion
    wsl_path = run_paths.to_wsl_path(run_paths.run_dir)
    assert "/" in wsl_path
    assert not ("\\" in wsl_path)


def test_wsl_eda_tools_accessible():
    """Verify that Python can invoke verilator, yosys, and iverilog inside WSL."""
    wsl_bin = shutil.which("wsl") or shutil.which("wsl.exe")
    if not wsl_bin:
        pytest.skip("WSL binary not found on host.")

    # 1. Test iverilog
    res_iverilog = subprocess.run(
        [wsl_bin, "--exec", "iverilog", "-V"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res_iverilog.returncode == 0
    assert "Icarus Verilog" in res_iverilog.stdout

    # 2. Test verilator
    res_verilator = subprocess.run(
        [wsl_bin, "--exec", "verilator", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res_verilator.returncode == 0
    assert "Verilator" in res_verilator.stdout

    # 3. Test yosys
    res_yosys = subprocess.run(
        [wsl_bin, "--exec", "yosys", "-V"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res_yosys.returncode == 0
    assert "Yosys" in res_yosys.stdout
