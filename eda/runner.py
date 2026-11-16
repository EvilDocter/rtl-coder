"""WSL Execution Engine for running EDA tools inside Ubuntu."""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple


class WSLCommandRunner:
    """Executes Linux CLI commands inside the Ubuntu WSL distribution."""

    def __init__(self, distro: Optional[str] = None):
        self.wsl_bin = shutil.which("wsl") or shutil.which("wsl.exe") or "wsl.exe"
        self.distro = distro  # Defaults to default WSL distro (Ubuntu-24.04)

    @staticmethod
    def to_wsl_path(path: Path) -> str:
        """Converts Windows paths (e.g. C:\\dir\\file) to WSL mount paths (/mnt/c/dir/file)."""
        resolved = str(path.resolve()).replace("\\", "/")
        if len(resolved) >= 2 and resolved[1] == ":":
            drive = resolved[0].lower()
            return f"/mnt/{drive}{resolved[2:]}"
        return resolved

    def run_command(
        self,
        command: List[str],
        cwd: Optional[Path] = None,
        timeout_seconds: float = 60.0,
        log_file: Optional[Path] = None,
    ) -> Tuple[int, str, str, float]:
        """Executes a command inside WSL.

        Returns: (exit_code, stdout, stderr, runtime_ms)
        """
        wsl_args = [self.wsl_bin]
        if self.distro:
            wsl_args.extend(["-d", self.distro])
        wsl_args.append("--exec")
        wsl_args.extend(command)

        start_time = time.perf_counter()
        exit_code = -1
        stdout = ""
        stderr = ""

        try:
            # If cwd is specified, change directory first in WSL if running directly
            workdir = str(cwd) if cwd else None
            proc = subprocess.run(
                wsl_args,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired:
            exit_code = -1
            stderr = f"Command timed out after {timeout_seconds} seconds"
        except Exception as e:
            exit_code = -1
            stderr = f"Failed to execute WSL command: {str(e)}"

        runtime_ms = (time.perf_counter() - start_time) * 1000.0

        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"=== Command: {' '.join(command)} ===\n")
                f.write(f"=== Exit Code: {exit_code} (Runtime: {runtime_ms:.2f}ms) ===\n\n")
                f.write("--- STDOUT ---\n")
                f.write(stdout)
                f.write("\n\n--- STDERR ---\n")
                f.write(stderr)

        return exit_code, stdout, stderr, runtime_ms
