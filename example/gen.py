#!/usr/bin/env python3
"""
Generate 10 demo task scripts into 0_gen/.

Usage:
    python gen.py

Each generated task script demonstrates basic worker behaviour:
- prints hostname and job identity ($WORKER_JOB_ID)
- queries GPU info via nvidia-smi
- sleeps for a variable duration to simulate different workloads
- prints CPU and memory info

After running this script, start a worker with:
    launch-worker .
or start multiple workers on Slurm with:
    bash launch.sh
"""

from pathlib import Path
from jinja2 import Template

TEMPLATE = Template("""\
#!/bin/bash
{
    echo "=== Task {{ task_id }} started ==="
    echo "Hostname:      $(hostname)"
    echo "Worker job ID: ${WORKER_JOB_ID}"
    echo "Date:          $(date)"
    echo ""

    echo "--- GPU info ---"
    nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader 2>/dev/null \\
        || echo "(nvidia-smi not available)"
    echo ""

    echo "--- CPU / memory ---"
    nproc
    free -h
    echo ""

    echo "--- Sleeping {{ sleep_seconds }}s to simulate workload ---"
    sleep {{ sleep_seconds }}

    echo ""
    echo "=== Task {{ task_id }} done ==="
}
""")

GEN_DIR = Path(__file__).parent / "0_gen"
PENDING_DIR = Path(__file__).parent / "1_pending"


def generate_task(
    task_id: int,
    sleep_seconds: int,
) -> None:
    """Generate a single demo task script."""
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"demo-task-{task_id:02d}.sh"
    content = TEMPLATE.render(task_id=task_id, sleep_seconds=sleep_seconds)
    file_path = GEN_DIR / filename
    with open(file_path, "w") as f:
        _ = f.write(content)
    print(f"Generated {file_path}")


if __name__ == "__main__":
    for i in range(1, 11):
        generate_task(task_id=i, sleep_seconds=i * 5)
    print(f"\n10 task scripts written to {GEN_DIR}")
    print(f"Copy them to {PENDING_DIR} and run 'launch-worker .' or 'launch.sh' (which uses launch-slurm-workers) to start processing them.")
