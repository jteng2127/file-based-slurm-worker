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
"""

from pathlib import Path
from string import Template

TEMPLATE = Template(
    """\
#!/bin/bash

echo "=== Task ${task_id} started ==="
echo "Hostname:      $$(hostname)"
echo "Worker job ID: $${WORKER_JOB_ID}"
echo "Date:          $$(date)"
echo ""

echo "--- GPU info ---"
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader 2>/dev/null \
    || echo "(nvidia-smi not available)"
echo ""

echo "--- CPU / memory ---"
nproc
free -h
echo ""

echo "--- Sleeping ${sleep_seconds}s to simulate workload ---"
sleep ${sleep_seconds}

echo ""
echo "=== Task ${task_id} done ==="
"""
)


def generate_task(out_dir: Path, task_id: int, sleep_seconds: int) -> None:
    """Generate a single demo task script."""
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"demo-task-{task_id:02d}.sh"
    content = TEMPLATE.substitute(task_id=task_id, sleep_seconds=sleep_seconds)
    file_path = out_dir / filename
    with open(file_path, "w") as f:
        _ = f.write(content)
    print(f"Generated {file_path}")


if __name__ == "__main__":
    out_dir = Path(__file__).parent / "0_gen"
    for i in range(1, 11):
        generate_task(out_dir, task_id=i, sleep_seconds=i * 5)
    print(f"\n10 task scripts written to {out_dir}")
    print("Copy them to 1_pending/ and run 'launch-worker .' to start processing them.")

