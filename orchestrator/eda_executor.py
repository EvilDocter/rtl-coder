"""Real EDA Tool Executor for the Orchestrator Pipeline."""

from pathlib import Path
from typing import List

from eda import IVerilogWrapper, ToolReport, ToolStatus, VerilatorWrapper, YosysWrapper
from orchestrator.state_machine import PipelineContext


class RealEDAExecutor:
    """Executes the complete EDA toolchain on generated RTL and testbench collateral."""

    def __init__(self):
        self.verilator = VerilatorWrapper()
        self.iverilog = IVerilogWrapper()
        self.yosys = YosysWrapper()

    def __call__(self, ctx: PipelineContext) -> List[ToolReport]:
        reports: List[ToolReport] = []

        if not ctx.rtl or not ctx.rtl.file_path or not ctx.rtl.file_path.exists():
            return reports

        reports_dir = ctx.run_paths.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        iter_prefix = f"iter_{ctx.iteration}"

        # -------------------------------------------------------------
        # 1. Lint Stage (Verilator)
        # -------------------------------------------------------------
        lint_log = reports_dir / f"{iter_prefix}_lint.log"
        lint_report = self.verilator.lint(
            source_files=[ctx.rtl.file_path],
            top_module=ctx.rtl.top_module,
            log_file=lint_log,
        )
        reports.append(lint_report)

        # -------------------------------------------------------------
        # 2. Logic Synthesis Stage (Yosys)
        # -------------------------------------------------------------
        synth_log = reports_dir / f"{iter_prefix}_synth.log"
        netlist_out = reports_dir / f"{ctx.rtl.module_name}_syn.v"
        synth_report = self.yosys.synthesize(
            source_files=[ctx.rtl.file_path],
            top_module=ctx.rtl.top_module,
            output_netlist=netlist_out,
            log_file=synth_log,
        )
        reports.append(synth_report)

        # -------------------------------------------------------------
        # 3. Compilation & Simulation Stage (Icarus Verilog)
        # -------------------------------------------------------------
        if ctx.verification and ctx.verification.file_path and ctx.verification.file_path.exists():
            compile_log = reports_dir / f"{iter_prefix}_compile.log"
            vvp_out = reports_dir / f"{ctx.rtl.module_name}.vvp"

            c_report = self.iverilog.compile(
                source_files=[ctx.rtl.file_path, ctx.verification.file_path],
                output_vvp=vvp_out,
                log_file=compile_log,
            )
            reports.append(c_report)

            if c_report.status == ToolStatus.PASS and vvp_out.exists():
                sim_log = reports_dir / f"{iter_prefix}_sim.log"
                s_report = self.iverilog.simulate(
                    vvp_file=vvp_out,
                    log_file=sim_log,
                    cwd=reports_dir,
                )
                reports.append(s_report)

        return reports
