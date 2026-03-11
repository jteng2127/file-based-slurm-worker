# file-based-slurm-worker

A filesystem-based task queue for running many independent jobs across parallel Slurm workers.

## Why do I need this?

- **Simple pipeline**: Your task queue is just a directory. Move a script into `1_pending/`, launch some workers, watch tasks go through `2_running/`, `3_done/` or `4_failed/`, and log to `5_task_logs/`. No daemons, no databases.
- **Simple control**: Control your tasks and workers by moving or deleting files. No complex APIs or commands.
- **Race-free parallelism**: Run as many workers as you want locally or on Slurm. No task ever runs twice.
- **Automatic recovery**: If a worker is killed mid-task, the task will automatically retry on another worker.
- **NCHC-Slurm-ready**: Auto-detects NCHC Slurm clusters (twcc, nano4, nano5) and sets the sbatch arguments for you. How many nodes? How many GPUs per worker? How many workers? That's all you need to provide.

## Quick start

### 1. Install

```bash
git clone https://github.com/jteng2127/file-based-slurm-worker.git
cd file-based-slurm-worker
bash install
source ~/.zshrc   # or source ~/.bashrc
```

### 2. Generate example tasks

```bash
cd example/
python gen.py
# creates 10 demo scripts in example/0_gen/
mkdir -p 1_pending/
cp 0_gen/*.sh 1_pending/
```

### 3a. Run workers locally

Open two terminals, run the following command in each:

```bash
launch-worker .
# processes all tasks in 1_pending/, move running tasks to 2_running/
# move tasks to 3_done/ or 4_failed/ based on exit code
# task logs go to 5_task_logs/
# worker status files go to 7_worker_status/
```

### 3b. Run workers on Slurm

```bash
bash launch.sh
# submits a Slurm job with 4 parallel workers
# Slurm job and worker logs go to 6_job_logs/
```

## How it works

Tasks are shell scripts placed in a `1_pending/` directory. Workers race to pick them up, move them through a set of numbered state directories, and log their output.

```
task-dir/
  1_pending/        task scripts (.sh) waiting to run
  2_running/        task currently being executed (moved here atomically)
  3_done/           completed tasks (exit code 0)
  4_failed/         failed tasks (non-zero exit code)
  5_task_logs/      stdout/stderr for each task run
  6_job_logs/       Slurm job logs
  7_worker_status/  one file per active worker with current status
```

Multiple workers poll `1_pending/` concurrently. A task file is claimed by `mv` it into `2_running/`, which is atomic on most filesystems, so each task runs on exactly one worker.

If a worker is terminated (recieved SIGTERM or SIGINT) while running a task, the task file is moved back to `1_pending/` automatically, so it will be retried by any remaining worker.

## How to use

### 1. Prepare task scripts

- Create a task directory, e.g. `task-dir/`
- `cd task-dir`, generate scripts using a generator script, e.g. [example](example/gen.py), outputs to `0_gen/`
- Scripts must be `.sh` files; the worker sets `WORKER_JOB_ID` (`<worker_id>.<job_count>`) before each run
- Review generated scripts, then move them to `1_pending/`

### 2. Launch workers

Run locally with `launch-worker` or on Slurm with `launch-slurm-workers`. See [Commands](#commands) for full options.

For Slurm, each Slurm task maps to one worker, so the total number of workers is `-N` (nodes) × `-n` (tasks per node), and each worker gets `-g` GPUs.

```bash
launch-slurm-workers -N 2 -n 4 -g 1 task-dir/
# submits a job with 8 workers (2 nodes × 4 tasks), each using 1 GPU
```

### 3. Monitor and control

- Watch task states via the directory layout (`2_running/`, `3_done/`, `4_failed/`, etc.)
- Stop all workers gracefully for a job: `scancel <JOB_ID>`
- Stop a specific worker gracefully: `rm task-dir/7_worker_status/<WORKER_ID>`
- Stop a task by removing it from `2_running/`
- Workers can auto-terminate if they fail too many consecutive tasks. Enable this with `launch-slurm-workers --max-consecutive-fails MAX`.
- Move failed tasks back to pending: `launch-slurm-workers --reset-failed TASK_DIR` or manually `mv task-dir/4_failed/*.sh task-dir/1_pending/`

## Commands

### `launch-slurm-workers [options] TASK_DIR`

Submit a Slurm job that starts multiple workers in parallel using `srun`.

```
Options:
  -a, --account ACCOUNT        Slurm account
  -N, --nodes N                Number of nodes (default: 1)
  -n, --ntasks-per-node N      Tasks (workers) per node (default: 1)
  -g, --gpu-per-task N         GPUs per task/worker (default: 1)
  -i, --max-idle SECONDS       Worker idle timeout in seconds (default: 0, 0 means run forever)
  -f, --max-consecutive-fails MAX Max consecutive task failures before worker auto-terminates (default: 0, disabled)
  --task-estimate-second SEC   Task execution time estimate in seconds (default: 0)
  --sb--KEY VALUE              Pass --KEY=VALUE directly to sbatch (e.g. --sb--partition dev, --sb--time 1:00:00)
  --sb-K VALUE                 Pass -K=VALUE directly to sbatch (e.g. --sb-p dev, --sb-t 1:00:00)
  -y, --yes                    Skip confirmation prompt
  --reset-failed               Move 4_failed/ tasks back to 1_pending/ before submitting (default: no)
  --clean-logs                 Delete 5_task_logs/ and 6_job_logs/ before submitting (default: no)
  --log-system-metrics          Log system metrics (GPU, CPU, Memory) before each task (default: no)
  -h, --help                   Show this help message
```

Platform presets (auto-detected from hostname):

| Platform        | Hostname pattern | Partition | Time       | Mem/GPU | CPU/task |
|-----------------|------------------|-----------|------------|---------|----------|
| twcc            | `un-ln*`         | gp4d      | 4-00:00:00 | 90 GB   | 4        |
| nano5           | `cbi-lgn*`       | normal    | 2-00:00:00 | 200 GB  | 12×GPU   |
| nano4           | `25a-lgn*`       | normal    | 1-00:00:00 | 200 GB  | 12×GPU   |
| nano4 (dev)     | `25a-lgn*`       | dev       | 02:00:00   | 200 GB  | 12×GPU   |
| (other/generic) | —                | normal    | 00:30:00   | 16 GB   | 4        |

**Task Time limit**: If `--task-estimate-second` is provided (> 0), workers will stop pulling new tasks from `1_pending/` when the remaining SLURM job time is less than the specified estimate. This prevents tasks from being killed midway due to the Slurm job reaching its maximum `--time` limit.

The script automatically cancels the Slurm job once all workers finish or go idle.

### `launch-worker TASK_DIR [MAX_IDLE] [ACCEPT_TASK_TIME_SECOND_LIMIT] [LOG_SYSTEM_METRICS] [MAX_CONSECUTIVE_FAILS]`

Start a single worker process that consumes tasks from `TASK_DIR/1_pending/`.

```
Arguments:
  TASK_DIR                      Directory containing 1_pending/
  MAX_IDLE                      Seconds to wait with no tasks before exiting (default: 0, 0 means run forever)
  ACCEPT_TASK_TIME_SECOND_LIMIT Limit in seconds after which the worker stops accepting new tasks (default: 0, 0 means no limit)
  LOG_SYSTEM_METRICS            1 to log system metrics before each task, 0 otherwise (default: 0)
  MAX_CONSECUTIVE_FAILS         Max consecutive task failures before worker auto-terminates (default: 0, disabled)
```

The worker exits after being idle for `MAX_IDLE` seconds. It handles `SIGINT` and `SIGTERM` gracefully: the running task's process tree is killed, and the task file is returned to `1_pending/`.

You can run multiple workers pointing at the same `TASK_DIR` at the same time.
