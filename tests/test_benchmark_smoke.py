"""Keep scripts/benchmark.py from rotting.

Runs the smoke pass (iterations=2 each) and asserts the script exits cleanly.
Not a perf gate — just a "does it import + execute end-to-end" guard. Useful
because the script is referenced from the audit-plan as the canonical
regression sentinel for round-driver throughput.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_benchmark_smoke_runs() -> None:
    script = Path(__file__).parent.parent / "scripts" / "benchmark.py"
    result = subprocess.run(
        [sys.executable, str(script), "--smoke"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"benchmark.py --smoke exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
