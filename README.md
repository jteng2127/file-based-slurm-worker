# slurm-task-worker

A filesystem-based task queue for running many independent jobs across parallel Slurm workers.

Tasks are shell scripts placed in a `1_pending/` directory. Workers race to pick them up, move
them through a set of numbered state directories, and log their output.

---

## How it works

```
task-dir/
  1_pending/        task scripts (.sh) waiting to run
  2_running/        task currently being executed (moved here atomically)
  3_done/           completed tasks (exit code 0)
  4_failed/         failed tasks (non-zero exit code)
  5_task_logs/      stdout/stderr for each task run
  6_job_logs/       Slurm job logs (created by launch-slurm-workers)
  7_worker_status/  one file per active worker with current status
```

Multiple workers poll `1_pending/` concurrently. A task file is claimed by `mv`-ing it into
`2_running/`, which is atomic on most shared filesystems — so each task runs on exactly one
worker, no matter how many workers are active.

If a worker is terminated while running a task, the task file is moved back to `1_pending/`
automatically (via a signal trap), so it will be retried by any remaining worker.

A worker also monitors its own status file in `7_worker_status/`. Removing that file causes the
worker to shut itself down gracefully — a convenient way to stop individual workers.

---

## Task script format

Tasks are plain shell scripts with a `.sh` extension. The worker sets one extra environment
variable before executing each task:

- `WORKER_JOB_ID` — unique ID for the specific task run, format `<worker_id>.<job_count>`

Example task script:

```bash
#!/bin/bash
echo "Running on $(hostname), job $WORKER_JOB_ID"
python train.py --config config.yaml
```

---

## Install

```bash
git clone https://github.com/your-username/slurm-task-worker.git
cd slurm-task-worker
bash install
source ~/.zshrc   # or source ~/.bashrc
```

The install script appends `bin/` to `PATH` in `~/.zshrc` and `~/.bashrc`.

---

## Commands

### `launch-worker TASK_DIR [MAX_IDLE]`

Start a single worker process that consumes tasks from `TASK_DIR/1_pending/`.

```
Arguments:
  TASK_DIR      Directory containing 1_pending/
  MAX_IDLE      Seconds to wait with no tasks before exiting (default: 60)
```

The worker exits after being idle for `MAX_IDLE` seconds. It handles `SIGINT` and `SIGTERM`
gracefully: the running task's process tree is killed, and the task file is returned to
`1_pending/`.

You can run multiple workers pointing at the same `TASK_DIR` at the same time — from multiple
terminals, SSH sessions, or Slurm array tasks.

---

### `launch-slurm-workers [options] TASK_DIR`

Submit a Slurm job that starts multiple workers in parallel using `srun`.

```
Options:
  -a, --account ACCOUNT        Slurm account
  -N, --nodes N                Number of nodes (default: 1)
  -n, --ntasks-per-node N      Tasks (workers) per node (default: 1)
  -g, --gpu-per-task N         GPUs per task/worker (default: 1)
  -i, --max-idle SECONDS       Worker idle timeout in seconds (default: 60)
  -p, --partition PARTITION    Slurm partition (default: platform-dependent)
  -t, --time TIME              Slurm time limit (overrides platform default)
  --mem-per-gpu MEM            Memory per GPU in GB (overrides platform default)
  --cpus-per-task N            CPUs per task (overrides platform default)
  --sb-KEY VALUE               Pass --KEY=VALUE directly to sbatch
  -y, --yes                    Skip confirmation prompt
  --reset-failed               Move 4_failed/ tasks back to 1_pending/ before submitting
  --clean-logs                 Delete 5_task_logs/ and 6_job_logs/ before submitting
  -h, --help                   Show this help message
```

Platform presets (auto-detected from hostname):

| Platform        | Hostname pattern | Partition | Time       | Mem/GPU | CPU/task |
|-----------------|------------------|-----------|------------|---------|----------|
| twcc            | `un-ln*`         | gp4d      | 4-00:00:00 | 90 GB   | 4        |
| nano5           | `cbi-lgn*`       | normal    | 2-00:00:00 | 200 GB  | 12×GPU   |
| nano4           | `25a-lgn*`       | normal    | 1-00:00:00 | 200 GB  | 13×GPU   |
| nano4 (dev)     | `25a-lgn*`       | dev       | 2:00:00    | 200 GB  | 13×GPU   |
| (other/generic) | —                | normal    | 00:30:00   | 16 GB   | 4        |

Any platform value can be overridden with `-t`, `--mem-per-gpu`, or `--cpus-per-task`.

The script automatically cancels the Slurm job once all workers finish or go idle.

---

## Example

```bash
cd example/

# Generate 10 demo task scripts into 1_pending/
python gen.py

# Option A: run locally with one worker
launch-worker .

# Option B: submit to Slurm (NCHC twcc, 2 workers on 1 node)
cd ..
launch-slurm-workers -n 2 example/
```

---

## Controlling workers

- Kill all workers for a job: `scancel <JOB_ID>`
- Stop a specific worker gracefully: `rm task-dir/7_worker_status/<WORKER_ID>`
- Move failed tasks back to pending: `launch-slurm-workers --reset-failed TASK_DIR` (or manually
  `mv task-dir/4_failed/*.sh task-dir/1_pending/`)
