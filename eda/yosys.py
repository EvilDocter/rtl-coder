"""Yosys Logic Synthesis and Cell Area Reporting Wrapper."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eda.models import ToolMessage, ToolMessageSeverity, ToolReport, ToolStatus
from eda.runner import WSLCommandRunner


class YosysWrapper:
    """Automates logic synthesis, syntax elaboration, and cell counting with Yosys."""

    def __init__(self, runner: Optional[WSLCommandRunner] = None):
        self.runner = runner or WSLCommandRunner()

    def parse_synthesis_output(self, stdout: str, stderr: str) -> Tuple[List[ToolMessage], Dict[str, Any]]:
        """Parses errors, warnings, and circuit cell statistics from Yosys logs."""
        messages: List[ToolMessage] = []
        metrics: Dict[str, Any] = {
            "total_cells": 0,
            "dff_count": 0,
            "logic_cells": 0,
            "wires": 0,
            "wire_bits": 0,
        }
        combined = f"{stdout}\n{stderr}"

        # 1. Parse Errors & Warnings
        # Example: ERROR: Module `\counter' contains a combinational loop!
        # Example: /path/file.v:32: ERROR: Identifier `\xyz' is implicitly declared
        # Example: Warning: Identifier `\rst' is used but not defined!
        error_pattern = re.compile(
            r"^(?:([^:\n\r]+):(\d+):\s*)?(ERROR|Warning):\s*(.*)$",
            re.MULTILINE | re.IGNORECASE
        )
        for match in error_pattern.finditer(combined):
            filepath, line_str, tag, msg = match.groups()
            tag_upper = tag.upper()
            severity = ToolMessageSeverity.ERROR if tag_upper == "ERROR" else ToolMessageSeverity.WARNING
            line = int(line_str) if line_str else None
            fname = Path(filepath).name if filepath else None

            messages.append(
                ToolMessage(
                    severity=severity,
                    file=fname,
                    line=line,
                    code=tag_upper,
                    message=msg.strip(),
                )
            )

        # 2. Parse Circuit Statistics
        # Look for:
        #   Number of wires:                 12
        #   Number of wire bits:             34
        #   Number of public wires:          12
        #   Number of public wire bits:      34
        #   Number of cells:                 18
        #     $_DFF_P_                        8
        #     $_AND_                          4
        total_cells_m = re.search(r"Number of cells:\s+(\d+)", combined)
        if total_cells_m:
            metrics["total_cells"] = int(total_cells_m.group(1))

        wires_m = re.search(r"Number of wires:\s+(\d+)", combined)
        if wires_m:
            metrics["wires"] = int(wires_m.group(1))

        wire_bits_m = re.search(r"Number of wire bits:\s+(\d+)", combined)
        if wire_bits_m:
            metrics["wire_bits"] = int(wire_bits_m.group(1))

        # Count D-Flip-Flops (e.g. $_DFF_, $_SDFFE_PN0P_, etc.)
        dff_matches = re.findall(r"(\$_[A-Z0-9_]*DFF[A-Z0-9_]*|\bFDRE\b|\bdff\b)\s+(\d+)", combined)
        dff_count = sum(int(count) for _, count in dff_matches)
        metrics["dff_count"] = dff_count
        metrics["logic_cells"] = max(0, metrics["total_cells"] - dff_count)

        return messages, metrics

    def synthesize(
        self,
        source_files: List[Path],
        top_module: str,
        output_netlist: Optional[Path] = None,
        log_file: Optional[Path] = None,
    ) -> ToolReport:
        """Executes synthesis flow in Yosys and extracts hardware area statistics."""
        wsl_sources = " ".join([f'"{self.runner.to_wsl_path(f)}"' for f in source_files])

        script_cmds = [
            f"read_verilog -sv {wsl_sources};",
            f"hierarchy -check -top {top_module};",
            "proc;",
            "opt;",
            "fsm;",
            "opt;",
            "memory;",
            "opt;",
            "techmap;",
            "opt;",
        ]

        if output_netlist:
            output_netlist.parent.mkdir(parents=True, exist_ok=True)
            wsl_out = self.runner.to_wsl_path(output_netlist)
            script_cmds.append(f'write_verilog "{wsl_out}";')

        script_cmds.append("stat;")
        full_command_str = " ".join(script_cmds)

        cmd = ["yosys", "-p", full_command_str]
        exit_code, stdout, stderr, runtime = self.runner.run_command(cmd, log_file=log_file)

        messages, metrics = self.parse_synthesis_output(stdout, stderr)
        error_count = sum(1 for m in messages if m.severity == ToolMessageSeverity.ERROR)
        warning_count = sum(1 for m in messages if m.severity == ToolMessageSeverity.WARNING)

        status = ToolStatus.PASS if (exit_code == 0 and error_count == 0) else ToolStatus.FAIL

        return ToolReport(
            tool_name="yosys",
            stage="synth",
            status=status,
            exit_code=exit_code,
            messages=messages,
            error_count=error_count,
            warning_count=warning_count,
            runtime_ms=runtime,
            raw_log_path=log_file,
            stdout=stdout,
            stderr=stderr,
            metrics=metrics,
        )
