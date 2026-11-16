"""Automated test suite for Phase 3: EDA Tool Wrappers."""

from pathlib import Path
import pytest

from eda import IVerilogWrapper, ToolStatus, VerilatorWrapper, YosysWrapper

REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGNS_DIR = REPO_ROOT / "designs"


@pytest.fixture
def counter_files():
    return {
        "rtl": DESIGNS_DIR / "counter" / "counter.v",
        "tb": DESIGNS_DIR / "counter" / "tb_counter.v",
    }


@pytest.fixture
def fifo_files():
    return {
        "rtl": DESIGNS_DIR / "fifo" / "fifo_sync.v",
        "tb": DESIGNS_DIR / "fifo" / "tb_fifo_sync.v",
    }


@pytest.fixture
def broken_fsm_files():
    return {
        "rtl": DESIGNS_DIR / "fsm" / "fsm_detector.v",
        "tb": DESIGNS_DIR / "fsm" / "tb_fsm_detector.v",
    }


# -------------------------------------------------------------------------
# Verilator Lint Tests
# -------------------------------------------------------------------------

def test_verilator_lint_passing_counter(counter_files, tmp_path):
    """Verilator should pass cleanly on valid counter RTL."""
    wrapper = VerilatorWrapper()
    report = wrapper.lint(
        source_files=[counter_files["rtl"]],
        top_module="counter",
        log_file=tmp_path / "counter_lint.log",
    )
    assert report.status == ToolStatus.PASS
    assert report.error_count == 0
    assert report.exit_code == 0
    assert report.raw_log_path.exists()


def test_verilator_lint_passing_fifo(fifo_files, tmp_path):
    """Verilator should pass cleanly on valid FIFO RTL."""
    wrapper = VerilatorWrapper()
    report = wrapper.lint(
        source_files=[fifo_files["rtl"]],
        top_module="fifo_sync",
        log_file=tmp_path / "fifo_lint.log",
    )
    assert report.status == ToolStatus.PASS
    assert report.error_count == 0


def test_verilator_lint_detects_broken_fsm(broken_fsm_files, tmp_path):
    """Verilator must detect errors/warnings in the deliberately broken FSM."""
    wrapper = VerilatorWrapper()
    report = wrapper.lint(
        source_files=[broken_fsm_files["rtl"]],
        top_module="fsm_detector",
        log_file=tmp_path / "fsm_lint.log",
    )
    # The broken FSM has undefined identifier and width mismatches
    assert report.status == ToolStatus.FAIL or len(report.messages) > 0
    assert any(m.file == "fsm_detector.v" for m in report.messages)
    assert any(m.line is not None for m in report.messages)


# -------------------------------------------------------------------------
# Icarus Verilog Compilation & Simulation Tests
# -------------------------------------------------------------------------

def test_iverilog_compile_and_sim_counter(counter_files, tmp_path):
    """iverilog must compile and simulate the counter testbench, generating waveforms."""
    wrapper = IVerilogWrapper()
    vvp_out = tmp_path / "counter.vvp"
    compile_log = tmp_path / "counter_compile.log"
    sim_log = tmp_path / "counter_sim.log"

    # 1. Compile
    c_report = wrapper.compile(
        source_files=[counter_files["rtl"], counter_files["tb"]],
        output_vvp=vvp_out,
        log_file=compile_log,
    )
    assert c_report.status == ToolStatus.PASS
    assert c_report.error_count == 0
    assert vvp_out.exists()

    # 2. Simulate
    s_report = wrapper.simulate(
        vvp_file=vvp_out,
        log_file=sim_log,
        cwd=tmp_path,
    )
    assert s_report.status == ToolStatus.PASS
    assert s_report.exit_code == 0
    assert "ALL TESTS PASSED" in s_report.stdout
    # Waveform dump check
    assert s_report.waveform_path is not None
    assert s_report.waveform_path.name == "counter.vcd"


def test_iverilog_compile_and_sim_fifo(fifo_files, tmp_path):
    """iverilog must compile and simulate the FIFO testbench."""
    wrapper = IVerilogWrapper()
    vvp_out = tmp_path / "fifo.vvp"

    c_report = wrapper.compile(
        source_files=[fifo_files["rtl"], fifo_files["tb"]],
        output_vvp=vvp_out,
        log_file=tmp_path / "fifo_compile.log",
    )
    assert c_report.status == ToolStatus.PASS

    s_report = wrapper.simulate(
        vvp_file=vvp_out,
        log_file=tmp_path / "fifo_sim.log",
        cwd=tmp_path,
    )
    assert s_report.status == ToolStatus.PASS
    assert "ALL TESTS PASSED" in s_report.stdout


def test_iverilog_detects_broken_fsm(broken_fsm_files, tmp_path):
    """iverilog must fail compilation on undefined identifiers in the broken FSM."""
    wrapper = IVerilogWrapper()
    vvp_out = tmp_path / "fsm.vvp"

    c_report = wrapper.compile(
        source_files=[broken_fsm_files["rtl"], broken_fsm_files["tb"]],
        output_vvp=vvp_out,
        log_file=tmp_path / "fsm_compile.log",
    )
    assert c_report.status == ToolStatus.FAIL
    assert c_report.error_count > 0
    assert any("fsm_detector.v" in (m.file or "") for m in c_report.messages)


# -------------------------------------------------------------------------
# Yosys Synthesis Tests
# -------------------------------------------------------------------------

def test_yosys_synthesize_counter(counter_files, tmp_path):
    """Yosys must synthesize the counter and report cell counts."""
    wrapper = YosysWrapper()
    netlist_out = tmp_path / "counter_syn.v"
    synth_log = tmp_path / "counter_synth.log"

    report = wrapper.synthesize(
        source_files=[counter_files["rtl"]],
        top_module="counter",
        output_netlist=netlist_out,
        log_file=synth_log,
    )
    assert report.status == ToolStatus.PASS
    assert report.exit_code == 0
    assert netlist_out.exists()
    assert report.metrics["total_cells"] > 0
    assert report.metrics["dff_count"] == 8  # 8 D-flip-flops for 8-bit counter!


def test_yosys_synthesize_fifo(fifo_files, tmp_path):
    """Yosys must synthesize the FIFO and extract memory/cells."""
    wrapper = YosysWrapper()
    netlist_out = tmp_path / "fifo_syn.v"

    report = wrapper.synthesize(
        source_files=[fifo_files["rtl"]],
        top_module="fifo_sync",
        output_netlist=netlist_out,
        log_file=tmp_path / "fifo_synth.log",
    )
    assert report.status == ToolStatus.PASS
    assert report.metrics["total_cells"] > 0


def test_yosys_detects_broken_fsm(broken_fsm_files, tmp_path):
    """Yosys must fail synthesis on the broken FSM and report the error."""
    wrapper = YosysWrapper()

    report = wrapper.synthesize(
        source_files=[broken_fsm_files["rtl"]],
        top_module="fsm_detector",
        log_file=tmp_path / "fsm_synth.log",
    )
    assert report.status == ToolStatus.FAIL
    assert report.error_count > 0
