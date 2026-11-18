"""Verilator wrapper for static linting, design rule checking, and coverage."""

import re
from pathlib import Path
from typing import List, Optional

from eda.models import ToolMessage, ToolMessageSeverity, ToolReport, ToolStatus
from eda.runner import WSLCommandRunner


class VerilatorWrapper:
    """Automates static linting and coverage checks with Verilator."""

    def __init__(self, runner: Optional[WSLCommandRunner] = None):
        self.runner = runner or WSLCommandRunner()

    def parse_lint_output(self, stdout: str, stderr: str) -> List[ToolMessage]:
        """Parses Verilator diagnostic output.

        Example formats:
        %Error: counter.v:14:5: syntax error, unexpected assign
        %Warning-WIDTH: counter.v:22:10: Operator ASSIGN expects 8 bits on the Assign RHS, but Assign RHS's CONST '32'h0' generates 32 bits.
        %Warning-COMBDLY: fsm.v:45:8: Delayed assignments (<=) in non-clocked always block
        """
        messages: List[ToolMessage] = []
        combined = f"{stdout}\n{stderr}"

        # Pattern: %(Error|Warning)(?:-([A-Z0-9_]+))?:\s*([^:\n\r]+):(\d+):(?:(\d+):)?\s*(.*)$
        pattern = re.compile(
            r"^\s*%(Error|Warning)(?:-([A-Z0-9_]+))?:\s*([^:\n\r]+):(\d+):(?:(\d+):)?\s*(.*)$",
            re.MULTILINE
        )

        for match in pattern.finditer(combined):
            kind, tag, filepath, line_str, col_str, msg = match.groups()
            severity = ToolMessageSeverity.ERROR if kind == "Error" else ToolMessageSeverity.WARNING
            line = int(line_str) if line_str else None
            col = int(col_str) if col_str else None

            messages.append(
                ToolMessage(
                    severity=severity,
                    file=Path(filepath).name,
                    line=line,
                    col=col,
                    code=tag or kind,
                    message=msg.strip(),
                )
            )

        return messages

    def lint(
        self,
        source_files: List[Path],
        top_module: Optional[str] = None,
        log_file: Optional[Path] = None,
        extra_args: Optional[List[str]] = None,
        ignore_warnings: Optional[List[str]] = None,
    ) -> ToolReport:
        """Runs Verilator in lint-only mode across source files."""
        wsl_sources = [self.runner.to_wsl_path(f) for f in source_files]

        cmd = ["verilator", "--lint-only", "-Wall", "-Wno-DECLFILENAME", "-Wno-EOFNEWLINE"]
        if top_module:
            cmd.extend(["--top-module", top_module])
        if ignore_warnings:
            for w in ignore_warnings:
                cmd.append(f"-Wno-{w}")
        if extra_args:
            cmd.extend(extra_args)
        cmd.extend(wsl_sources)

        exit_code, stdout, stderr, runtime = self.runner.run_command(cmd, log_file=log_file)
        messages = self.parse_lint_output(stdout, stderr)

        error_count = sum(1 for m in messages if m.severity == ToolMessageSeverity.ERROR)
        warning_count = sum(1 for m in messages if m.severity == ToolMessageSeverity.WARNING)

        # In strict linting, any %Error fails, and exit_code != 0 fails
        status = ToolStatus.PASS if (exit_code == 0 and error_count == 0) else ToolStatus.FAIL

        return ToolReport(
            tool_name="verilator",
            stage="lint",
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
