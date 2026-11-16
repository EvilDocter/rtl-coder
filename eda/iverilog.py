"""Icarus Verilog (iverilog & vvp) wrapper for compilation and simulation."""

import re
from pathlib import Path
from typing import List, Optional, Tuple

from eda.models import ToolMessage, ToolMessageSeverity, ToolReport, ToolStatus
from eda.runner import WSLCommandRunner


class IVerilogWrapper:
    """Automates compilation with iverilog and execution with vvp."""

    def __init__(self, runner: Optional[WSLCommandRunner] = None):
        self.runner = runner or WSLCommandRunner()

    def parse_compile_output(self, stdout: str, stderr: str) -> List[ToolMessage]:
        """Parses iverilog compile error/warning messages.

        Format example:
        counter.v:15: error: Unknown signal `rst_n' in this context.
        counter.v:22: warning: Timing controls are ignored in synthesizable contexts.
        counter.v:10: syntax error
        """
        messages: List[ToolMessage] = []
        combined = f"{stdout}\n{stderr}"

        # Pattern: <file>:<line>: <severity/type>: <message>
        pattern = re.compile(r"^([^:\n\r]+):(\d+):\s*(error|warning|syntax error)?(?::\s*)?(.*)$", re.MULTILINE | re.IGNORECASE)

        for match in pattern.finditer(combined):
            filepath, line_str, tag, msg = match.groups()
            line = int(line_str)
            tag_lower = (tag or "").lower()

            if "error" in tag_lower or "syntax" in tag_lower:
                severity = ToolMessageSeverity.ERROR
            elif "warning" in tag_lower:
                severity = ToolMessageSeverity.WARNING
            else:
                severity = ToolMessageSeverity.INFO

            full_msg = f"{tag}: {msg}".strip(" :") if tag else msg.strip()
            messages.append(
                ToolMessage(
                    severity=severity,
                    file=Path(filepath).name,
                    line=line,
                    code=tag or "compile_msg",
                    message=full_msg,
                )
            )

        return messages

    def parse_simulation_output(self, stdout: str, stderr: str, exit_code: int) -> Tuple[ToolStatus, List[ToolMessage]]:
        """Parses vvp simulation output and determines PASS/FAIL."""
        messages: List[ToolMessage] = []
        combined = f"{stdout}\n{stderr}"

        # Look for typical hardware testbench failure indicators
        has_fatal = bool(re.search(r"(\$fatal|FATAL|ASSERTION FAILED|FAILED|ERROR:)", combined, re.IGNORECASE))
        has_pass = bool(re.search(r"(ALL TESTS PASSED|PASSED|\$finish called)", combined, re.IGNORECASE))

        # Check for runtime errors
        for line in combined.splitlines():
            line_clean = line.strip()
            if any(token in line_clean.lower() for token in ["error", "fatal", "fail"]):
                messages.append(
                    ToolMessage(
                        severity=ToolMessageSeverity.ERROR,
                        message=line_clean,
                    )
                )
            elif "warning" in line_clean.lower():
                messages.append(
                    ToolMessage(
                        severity=ToolMessageSeverity.WARNING,
                        message=line_clean,
                    )
                )

        if exit_code != 0 or has_fatal:
            status = ToolStatus.FAIL
        elif has_pass:
            status = ToolStatus.PASS
        else:
            # If exit code 0 and no fatal, default to PASS
            status = ToolStatus.PASS

        return status, messages

    def compile(
        self,
        source_files: List[Path],
        output_vvp: Path,
        log_file: Optional[Path] = None,
        standard: str = "2012",
        extra_args: Optional[List[str]] = None,
    ) -> ToolReport:
        """Compiles Verilog/SystemVerilog sources into a vvp assembly binary."""
        output_vvp.parent.mkdir(parents=True, exist_ok=True)
        wsl_sources = [self.runner.to_wsl_path(f) for f in source_files]
        wsl_output = self.runner.to_wsl_path(output_vvp)

        cmd = ["iverilog", f"-g{standard}", "-Wall", "-o", wsl_output]
        if extra_args:
            cmd.extend(extra_args)
        cmd.extend(wsl_sources)

        exit_code, stdout, stderr, runtime = self.runner.run_command(cmd, log_file=log_file)
        messages = self.parse_compile_output(stdout, stderr)

        error_count = sum(1 for m in messages if m.severity == ToolMessageSeverity.ERROR)
        warning_count = sum(1 for m in messages if m.severity == ToolMessageSeverity.WARNING)

        status = ToolStatus.PASS if (exit_code == 0 and error_count == 0) else ToolStatus.FAIL

        return ToolReport(
            tool_name="iverilog",
            stage="compile",
            status=status,
            exit_code=exit_code,
            messages=messages,
            error_count=error_count,
            warning_count=warning_count,
            runtime_ms=runtime,
            raw_log_path=log_file,
            stdout=stdout,
            stderr=stderr,
        )

    def simulate(
        self,
        vvp_file: Path,
        log_file: Optional[Path] = None,
        cwd: Optional[Path] = None,
        timeout_seconds: float = 30.0,
    ) -> ToolReport:
        """Executes the compiled vvp simulation binary."""
        wsl_vvp = self.runner.to_wsl_path(vvp_file)
        cmd = ["vvp", wsl_vvp]

        workdir = cwd or vvp_file.parent
        exit_code, stdout, stderr, runtime = self.runner.run_command(
            cmd, cwd=workdir, timeout_seconds=timeout_seconds, log_file=log_file
        )

        status, messages = self.parse_simulation_output(stdout, stderr, exit_code)
        error_count = sum(1 for m in messages if m.severity == ToolMessageSeverity.ERROR)
        warning_count = sum(1 for m in messages if m.severity == ToolMessageSeverity.WARNING)

        # Check for generated .vcd waveform file
        vcd_candidates = list(workdir.glob("*.vcd"))
        waveform_path = vcd_candidates[0] if vcd_candidates else None

        return ToolReport(
            tool_name="vvp",
            stage="sim",
            status=status,
            exit_code=exit_code,
            messages=messages,
            error_count=error_count,
            warning_count=warning_count,
            runtime_ms=runtime,
            raw_log_path=log_file,
            stdout=stdout,
            stderr=stderr,
            waveform_path=waveform_path,
        )
